"""V183-6: the paper book sizes a short through the alert's one sizing path.

Alert share count == paper-book share count for a gap-sized short, a switch-off
stamp sizes exactly as before v183, a long record is byte-identical, and a
failure in the gap path falls back to stop-only sizing with one log line --
never to an unsized trade."""
import ast
import logging
import pathlib
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gap_sizing_mod
from swingbot.core.planning.plan_manager import PlanEvent, PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.scanning import execution_embeds, plan_table, scan_run, short_run, strategy_pass
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}
STOP_STAMP = {"rule": "stop", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}
REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "MAX_POSITION_VALUE_ABSOLUTE", 0.0)
    monkeypatch.setattr(config, "MAX_RISK_AMOUNT_ABSOLUTE", 0.0)
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 100.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def _short(**kw):
    base = dict(plan_id="s1", ticker="TSLA", direction="bearish", trigger_price=100.0,
                entry_price=None, stop_loss=102.0, tp1=96.0, tp2=92.0, gap_sizing=STAMP)
    base.update(kw)
    return _plan(**base)


def _log(tlog, plan):
    tlog.log_trade(
        ticker=plan.ticker, strategy="Bear Flag", horizon_key="4w", direction=plan.direction,
        confidence_level=3, confidence_label="Medium", entry=plan.trigger_price,
        stop_loss=plan.stop_loss, take_profit=plan.tp1, plan_id=plan.plan_id,
        gap_sizing=plan.gap_sizing)
    return tlog.trade_for_plan(plan.plan_id)


def test_a_gap_stamped_short_logs_the_gap_cut_share_count(tlog):
    record = _log(tlog, _short())
    assert record["shares"] == 25.0
    assert record["position_value"] == 2500.0
    assert record["sizing_mode"] == "risk_pct"
    assert record["gap_sizing"] == STAMP


def test_alert_and_paper_book_agree_on_shares(tlog):
    plan = _short()
    record = _log(tlog, plan)
    assert plan_table._sizing_snapshot(plan.trigger_price, plan)["shares"] == record["shares"]
    assert execution_embeds._ticket_money(plan).record_shares == record["shares"]


def test_record_plan_fill_resizes_through_the_stamp(tlog):
    plan = _short()
    _log(tlog, plan)
    tlog.record_plan_fill("s1", 100.5)
    record = tlog.trade_for_plan("s1")
    assert record["shares"] == gap_sizing_mod.size_for_trade(record, 100.5)["shares"]
    assert record["shares"] == plan_table._sizing_snapshot(100.5, plan)["shares"]
    assert record["shares"] < account.compute_position_size(100.5, 102.0)["shares"]
    assert record["gap_sizing"] == STAMP


def test_a_switch_off_stamp_sizes_on_the_stop_exactly(tlog):
    record = _log(tlog, _short(gap_sizing=STOP_STAMP))
    assert record["shares"] == account.compute_position_size(100.0, 102.0)["shares"] == 50.0
    assert record["gap_sizing"] == STOP_STAMP


def test_a_short_without_a_usable_p99_sizes_on_the_stop(tlog):
    stamp = {"rule": "gap_p99", "up_gap_p99_pct": None, "n_up_gaps": 12}
    record = _log(tlog, _short(gap_sizing=stamp))
    assert record["shares"] == 50.0
    assert record["gap_sizing"] == stamp


def test_a_long_record_carries_no_gap_key_and_todays_shares(tlog):
    long_plan = _plan(plan_id="l1", ticker="AAPL", direction="bullish", trigger_price=100.0,
                      stop_loss=95.0)
    record = _log(tlog, long_plan)
    assert "gap_sizing" not in record
    assert record["shares"] == account.compute_position_size(100.0, 95.0)["shares"] == 20.0


def test_a_gap_path_failure_falls_back_to_stop_sizing_with_one_log_line(tlog, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(gap_sizing_mod, "size_for", boom)
    with caplog.at_level(logging.INFO, logger="swingbot.core.tracking.performance"):
        record = _log(tlog, _short())
        tlog.record_plan_fill("s1", 100.5)
    lines = [r.getMessage() for r in caplog.records if "gap sizing fell back to stop" in r.getMessage()]
    assert lines == ["TSLA: gap sizing fell back to stop (boom)"] * 2
    assert record["shares"] == 50.0
    assert tlog.trade_for_plan("s1")["shares"] == account.compute_position_size(100.5, 102.0)["shares"]


def test_a_stop_sizing_failure_still_leaves_a_long_unsized_as_before(tlog, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("no balance")
    monkeypatch.setattr(account, "compute_position_size", boom)
    with caplog.at_level(logging.INFO):
        record = _log(tlog, _plan(plan_id="l1", direction="bullish"))
    assert record["shares"] is None and record["sizing_mode"] is None
    assert not [r for r in caplog.records if "fell back" in r.getMessage()]


class _Capture:
    def __init__(self):
        self.kw = None

    def log_trade(self, **kw):
        self.kw = kw
        return "t1"


def test_short_lane_log_trade_passes_the_plan_stamp(monkeypatch):
    capture = _Capture()
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(short_run, "trade_log", capture)
    monkeypatch.setattr(scan_run, "_logged_plan_fields", lambda *a: ([], None))
    monkeypatch.setattr(scan_run, "_persist_plan_v2", lambda *a: None)
    monkeypatch.setattr(scan_run, "_trade_quote", lambda *a: None)
    monkeypatch.setattr(scan_run, "_confidence_point_kwargs", lambda conf: {})
    item = SimpleNamespace(
        result=SimpleNamespace(ticker="TSLA", strategy="Bear Flag", horizon_key="4w", trend="bearish"),
        plan=SimpleNamespace(stop_sources=["swing"], target2_sources=[]),
        conf=SimpleNamespace(level=3, label="Medium", score=60, breakdown={}),
        plan_v2=_short(), level_map={}, combined_from=[])
    nums = {"entry": 100.0, "stop_loss": 102.0, "take_profit": 96.0, "target2": 92.0}
    short_run._log_trade(item, nums, "why", None, [])
    assert capture.kw["gap_sizing"] == STAMP
    item.plan_v2 = None
    short_run._log_trade(item, nums, "why", None, [])
    assert capture.kw["gap_sizing"] is None


def test_strategy_lane_open_trade_passes_the_plan_stamp():
    capture = _Capture()
    strategy_pass._open_trade(SimpleNamespace(trade_log=capture), _short(), ticker="TSLA",
                              strategy="Bear Flag", horizon="4w", direction="bearish")
    assert capture.kw["gap_sizing"] == STAMP


def test_plan_manager_fallback_fill_sizes_like_the_alert(tlog):
    """Review Focus 2: a fill with no placeholder logs the trade itself."""
    plan = _short(entry_price=100.0, status=PlanStatus.ACTIVE)
    mgr = PlanManager(PlanStore(), lambda *a, **k: None, trade_log=tlog)
    mgr._on_event(plan, PlanEvent(plan.plan_id, "filled", {}))
    record = tlog.trade_for_plan(plan.plan_id)
    assert record["shares"] == 25.0
    assert record["gap_sizing"] == STAMP


@pytest.mark.parametrize("path", [
    "swingbot/core/scanning/scan_run.py", "swingbot/core/scanning/short_run.py",
    "swingbot/core/scanning/strategy_pass.py", "swingbot/core/planning/plan_manager.py",
])
def test_every_log_trade_call_site_passes_gap_sizing(path):
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "log_trade"]
    assert calls, path
    for call in calls:
        assert "gap_sizing" in {kw.arg for kw in call.keywords}, (path, call.lineno)
