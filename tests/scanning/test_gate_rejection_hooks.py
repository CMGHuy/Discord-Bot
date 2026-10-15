"""v147 V147-10: each live block point (L1-L6) writes exactly one gate_rejections row with the
right gate/reason/margin, and a failing write leaves the scan result identical."""
import inspect
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.edge import rs_gate
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.plan_types import plan_from_dict
from swingbot.core.planning.stop_scope import plan_stop_ceiling
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from swingbot.core.scanning import (analyze, dedup, engine, qualify, rejection_recorder, scan_run,
                                    short_run)
from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv
from tests.scanning import test_engine_v2_plans as v2
from tests.scanning import test_rs_gate_wiring as rsw
from tests.scanning.test_rejection_recorder import _scenario
from tests.store_seed import seed_store

FRAME = make_ohlcv([100.0 + 0.1 * i for i in range(40)], start="2024-01-02")
BAR_DATE = FRAME.index[-1].date().isoformat()
HIGH_RS = 99.0          # above any laggard line: a bearish setup here is blocked


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    """Same isolation as test_engine_v2_plans.py: _sync_run_scan reads the account and
    writes telemetry, neither of which may touch the real data/."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0, "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    })


class FakeRepo:
    def __init__(self, fail=False):
        self.records, self.fail, self.attempts = [], fail, 0

    def insert_ignore(self, record):
        self.attempts += 1
        if self.fail:
            raise RuntimeError("database down")
        self.records.append(record)
        return True


def _use(monkeypatch, fake):
    monkeypatch.setattr(rejection_recorder, "_repo", lambda: fake)
    return fake


@pytest.fixture
def repo(monkeypatch):
    return _use(monkeypatch, FakeRepo())


# --- L1 / L2: the strategy pass ---------------------------------------------------------

class _Store:
    def all(self):
        return []

    def add(self, plan):
        raise AssertionError("a blocked signal must never be stored")


class _Log:
    def open_trade_for_ticker(self, ticker):
        return None


def _deps(rs=None):
    return sp._PassDeps(plan_store=_Store(), trade_log=_Log(), mode="live", live_allow=set(),
                        rs_combined_of=lambda ticker: rs, asof_of=None)


def _emit(deps, *, strategy="RSI", direction="bearish"):
    result = sp.PassResult()
    sp._emit_signal(result, FRAME, ticker="AAPL", strategy=strategy, direction=direction,
                    horizon="2w", bar_date=BAR_DATE, regime=None, deps=deps)
    return result


def test_strategy_rs_block_writes_one_row(repo):
    assert sp._rs_blocked("AAPL", "bearish", lambda ticker: HIGH_RS)
    result = _emit(_deps(rs=HIGH_RS))
    assert result.rs_blocked == 1
    (row,) = repo.records
    assert (row["gate"], row["reason"], row["source"]) == ("rs", "rs_blocked", "strategy")
    assert row["margin"] == pytest.approx(rs_gate.rs_margin(HIGH_RS))
    assert row["signal_date"] == BAR_DATE and row["strategy"] == "RSI" and row["horizon"] == "2w"


def test_strategy_compression_block_writes_one_row(repo, monkeypatch):
    monkeypatch.setattr(sp, "_dryup_blocked", lambda *a, **k: False)
    monkeypatch.setattr(sp, "_compression_context",
                        lambda *a, **k: ({"compression_mode": "isolated"}, "earnings_blackout"))
    result = _emit(_deps(), strategy=COMPRESSION_SHORT)
    assert result.compression_rejected == 1
    (row,) = repo.records
    assert (row["gate"], row["reason"], row["margin"]) == ("compression", "earnings_blackout", None)
    assert row["entry_context"] == {"compression_mode": "isolated"}


def test_an_unblocked_signal_with_no_plan_writes_nothing(repo, monkeypatch):
    monkeypatch.setattr(sp, "_dryup_blocked", lambda *a, **k: False)
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *a, **k: None)
    _emit(_deps(), direction="bullish")                 # O1: no geometry, not one of the gates
    assert repo.records == []


def test_a_failing_write_leaves_the_strategy_pass_identical(monkeypatch):
    ok = _use(monkeypatch, FakeRepo())
    expected = vars(_emit(_deps(rs=HIGH_RS)))
    down = _use(monkeypatch, FakeRepo(fail=True))
    assert vars(_emit(_deps(rs=HIGH_RS))) == expected
    assert ok.records and down.attempts == 1


# --- L3 / L4: the confluence merge in _sync_run_scan ------------------------------------

def _count_rs_blocks(monkeypatch) -> list:
    blocks, real = [], scan_run.rs_verdict

    def spy(*args, **kwargs):
        verdict = real(*args, **kwargs)
        if verdict["status"] == "block":
            blocks.append(args[0])
        return verdict
    monkeypatch.setattr(scan_run, "rs_verdict", spy)
    return blocks


def test_confluence_rs_block_writes_one_row_per_blocked_scenario(repo, monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", True)
    blocks = _count_rs_blocks(monkeypatch)
    items, _funnel = rsw._scan_with_funnel(ticker="AAPL", direction="bearish", rs=HIGH_RS)
    rows = [r for r in repo.records if r["source"] == "confluence"]
    assert items == [] and blocks, "fixture must block at least one bearish scenario"
    assert len(rows) == len(blocks)
    signal_date = rsw._structured_df().index[-1].date().isoformat()
    for row in rows:
        assert (row["gate"], row["reason"], row["direction"]) == ("rs", "rs_blocked", "bearish")
        assert row["margin"] == pytest.approx(rs_gate.rs_margin(HIGH_RS))
        assert row["signal_date"] == signal_date and row["signal_close"] is not None
        assert row["scenario"] is not None and row["plan"] is None


def _keys(items):
    return sorted((i.result.ticker, i.result.horizon_key, i.result.trend) for i in items)


def test_a_failing_write_leaves_the_confluence_scan_identical(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", True)
    ok = _use(monkeypatch, FakeRepo())
    items_ok, funnel_ok = rsw._scan_with_funnel(ticker="AAPL", direction="bullish", rs=HIGH_RS)
    down = _use(monkeypatch, FakeRepo(fail=True))
    items_down, funnel_down = rsw._scan_with_funnel(ticker="AAPL", direction="bullish", rs=HIGH_RS)
    assert ok.records and down.attempts == ok.attempts
    assert _keys(items_down) == _keys(items_ok) and funnel_down == funnel_ok


def test_confluence_plan_rejection_writes_one_no_plan_row(repo, monkeypatch, tmp_path,
                                                          stub_batch_fetch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "RS_GATE", False)        # every scenario must reach the plan stage
    v2._setup_minimal_scan(monkeypatch, tmp_path)
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: None)
    skipped, real_skip = [], scan_run._skip_rejected_plan
    monkeypatch.setattr(scan_run, "_skip_rejected_plan",
                        lambda item, rc: skipped.append(item) or real_skip(item, rc))
    monkeypatch.setattr(dedup, "dedup_scan_items", lambda items: [])
    engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=0)
    rows = [r for r in repo.records if r["gate"] == "plan_rejected"]
    assert skipped, "fixture must reject at least one plan"
    assert len(rows) == len(skipped)
    for row in rows:
        assert row["reason"] == "no_qualifying_target" and row["cf_status"] == "no-plan"
        assert row["resolved_at"] == row["created_at"] and row["plan"] is None
        assert row["margin"] is None and row["source"] == "confluence"


# --- analyze: the stamps the L4/L6 rows read --------------------------------------------

def test_risk_cap_rejection_stamps_the_plan_and_its_margin(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    item = SimpleNamespace(plan_v2=None)
    analyze.attach_plan_v2(item, v2._gc_scenario(), make_ohlcv([4194.30] * 60), "GC=F", "4w",
                           level_map=None)
    assert item.plan_v2_rejected == "risk_cap"
    plan = item.plan_v2_rejected_plan
    loss = planned_loss_pct(plan["trigger_price"], plan["stop_loss"])
    # v139: the cap is plan_stop_ceiling(plan) -- 2% unless arm S stored a ceiling.
    ceiling = plan_stop_ceiling(plan_from_dict(plan))
    assert ceiling == HARD_MAX_PLANNED_LOSS_PCT
    assert item.plan_v2_rejected_margin == pytest.approx(loss - ceiling)
    assert item.plan_v2_rejected_margin > 0


def test_no_qualifying_target_clears_any_earlier_stamp(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: None)
    item = SimpleNamespace(plan_v2=None, plan_v2_rejected_plan={"stale": 1},
                           plan_v2_rejected_margin=9.9)
    analyze.attach_plan_v2(item, v2._scenario(), make_ohlcv([100.0] * 60), "AAPL", "4w",
                           level_map=None)
    assert item.plan_v2_rejected == "no_qualifying_target"
    assert item.plan_v2_rejected_plan is None and item.plan_v2_rejected_margin is None


def test_scan_items_default_to_no_rejected_plan():
    item = analyze.ScanItem(result=None, plan=None, conf=None)
    assert item.plan_v2_rejected_plan is None and item.plan_v2_rejected_margin is None


# --- L5 / L6: the short lane ------------------------------------------------------------

def _short_item(ticker):
    return SimpleNamespace(result=SimpleNamespace(ticker=ticker, horizon_key="4w", trend="bearish"),
                           plan=_scenario(), rs_combined=HIGH_RS, plan_v2_rejected_plan=None,
                           plan_v2_rejected_margin=0.4, candidate_context={"source": "short_universe"})


_VERDICTS = {"AAA": lambda i: qualify.Rejected(i, "rs", "rs_blocked"),
             "BBB": lambda i: qualify.Rejected(i, "plan", "risk_cap"),
             "CCC": lambda i: qualify.Rejected(i, "confirmation", "awaiting_confirmation"),
             "DDD": lambda i: qualify.Accepted(i)}


def _run_short_lane(monkeypatch):
    monkeypatch.setattr(qualify, "qualify_short_item",
                        lambda candidate, item, context: _VERDICTS[item.result.ticker](item))
    lane = {"spy": None, "sector_of": {}, "etf_symbol_of": {}, "sector_frames": {},
            "regime": None, "regimes": None, "funnel": None}
    items = [_short_item(t) for t in _VERDICTS]
    kept = short_run._qualified_items(items, False, {t: FRAME for t in _VERDICTS}, lane)
    return [i.result.ticker for i in kept]


def test_short_lane_records_rs_and_plan_rejections_once(repo, monkeypatch):
    assert _run_short_lane(monkeypatch) == ["DDD"]
    assert [(r["ticker"], r["gate"], r["reason"], r["source"]) for r in repo.records] == [
        ("AAA", "rs", "rs_blocked", "short_lane"), ("BBB", "plan_rejected", "risk_cap", "short_lane")]
    assert repo.records[1]["margin"] == 0.4


def test_a_failing_write_leaves_the_short_lane_identical(monkeypatch):
    _use(monkeypatch, FakeRepo(fail=True))
    assert _run_short_lane(monkeypatch) == ["DDD"]


# --- where the hooks may not live -------------------------------------------------------

def test_no_hook_in_shared_or_worker_code():
    from swingbot.core.scanning import outlook_run, scan_replay
    for module in (qualify, outlook_run, scan_replay, analyze):
        assert "rejection_recorder" not in inspect.getsource(module), module.__name__
