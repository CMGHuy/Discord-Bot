"""v147 V147-14: the report's inputs -- TRAIN JSONL, the live table, live taken re-walks."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from swingbot import config
from swingbot.core.analytics import gate_counterfactual_inputs as gci
from swingbot.core.backtesting.blocked_recorder import gate_row, write_gate_rows
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2, simulate_exit
from tests.helpers import make_ohlcv

WARM = (100.0, 100.5, 99.5, 100.0)
TP1_BAR = (100.5, 103.0, 100.2, 102.5)
FLAT = (100.2, 100.6, 99.8, 100.3)


def _train(**kw):
    base = dict(population="train", arm="blocked", source="confluence", ticker="AAPL", strategy="Fibonacci",
                horizon="2w", direction="bullish", signal_date="2021-03-01", gate="plan_rejected",
                reason="risk_cap", margin=0.4, cf_status="filled", cf_r=-1.0, win=False,
                planned_loss_pct=2.4, expiry_bars=5)
    base.update(kw)
    return gate_row(**base)


def _plan(**kw) -> TradePlanV2:
    base = dict(plan_id="p1", ticker="AAPL", created_at="2024-01-04", source="confluence",
                strategy="Fibonacci", horizon_key="2w", direction="bullish", entry_type="market",
                trigger_price=100.0, entry_price=100.0, expiry_bars=3, stop_loss=95.0, tp1=102.0,
                tp1_fraction=0.5, tp2=105.0, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.CLOSED, status_history=[])
    base.update(kw)
    return TradePlanV2(**base)


def _bars(n_after=20):
    return make_ohlcv([WARM] * 3 + [TP1_BAR] + [FLAT] * (n_after - 1), start="2024-01-02")   # 01-04 = index 2


def _record(**kw):
    base = {"id": 1, "ticker": "AAPL", "gate": "rs", "strategy": "Fibonacci", "horizon": "2w",
            "signal_date": "2026-10-05", "cf_status": "filled", "reason": "rs_blocked", "margin": -3.0,
            "direction": "bearish", "source": "strategy", "plan": None, "cf_r": 0.8, "win": True,
            "created_at": dt.datetime(2026, 10, 5, 20, tzinfo=dt.timezone.utc), "resolved_at": None}
    base.update(kw)
    return base


# --- TRAIN -------------------------------------------------------------------

def test_train_rows_round_trip_from_every_file(tmp_path):
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_gate_rows([_train()], first)
    write_gate_rows([_train(gate="compression", reason="earnings_unknown", source="strategy",
                            margin=None, planned_loss_pct=None, in_sample=True)], second)
    with first.open("a", encoding="utf-8") as handle:
        handle.write("\n")                                   # a blank line is not a row
    rows = gci.load_train_rows([first, second])
    assert [r["gate"] for r in rows] == ["plan_rejected", "compression"]
    assert rows[0] == json.loads(json.dumps(_train()))


def test_a_train_rs_row_is_refused(tmp_path):
    path = tmp_path / "rs.jsonl"
    write_gate_rows([_train(gate="rs", reason="rs_blocked", source="strategy")], path)
    with pytest.raises(ValueError, match="live-only"):
        gci.load_train_rows([path])


def test_a_live_row_in_a_train_file_is_refused(tmp_path):
    path = tmp_path / "live.jsonl"
    write_gate_rows([_train(population="live")], path)
    with pytest.raises(ValueError, match="population"):
        gci.load_train_rows([path])


def test_a_missing_train_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        gci.load_train_rows([tmp_path / "nope.jsonl"])


def test_default_train_paths_cover_logs_and_the_vm_inputs_dir(monkeypatch, tmp_path):
    repo, data = tmp_path / "repo", tmp_path / "data"
    (repo / "logs").mkdir(parents=True)
    (data / "reports" / "inputs").mkdir(parents=True)
    for path in (repo / "logs" / "v147-blocked-confluence.jsonl", repo / "logs" / "other.jsonl",
                 data / "reports" / "inputs" / "v147-blocked-compression.jsonl"):
        path.write_text("", encoding="utf-8")
    monkeypatch.setattr(gci, "REPO_ROOT", repo)
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    assert [p.name for p in gci.default_train_paths()] == ["v147-blocked-confluence.jsonl",
                                                           "v147-blocked-compression.jsonl"]


# --- live blocked --------------------------------------------------------------

def test_pending_records_never_become_rows():
    assert gci.live_blocked_rows([_record(cf_status="pending", cf_r=None, win=None)]) == []


def test_an_rs_record_maps_onto_the_shared_row_shape():
    (row,) = gci.live_blocked_rows([_record()])
    assert row == gate_row(population="live", arm="blocked", source="strategy", ticker="AAPL",
                           strategy="Fibonacci", horizon="2w", direction="bearish",
                           signal_date="2026-10-05", gate="rs", reason="rs_blocked", margin=-3.0,
                           cf_status="filled", cf_r=0.8, win=True)


def test_a_risk_cap_record_carries_planned_loss_and_dollar_risk_from_its_stored_plan():
    plan = {"trigger_price": 100.0, "stop_loss": 97.0, "expiry_bars": 4}
    (row,) = gci.live_blocked_rows([_record(gate="plan_rejected", reason="risk_cap", margin=1.0,
                                            source="short_lane", plan=plan, cf_r=-1.0, win=False)])
    assert row["planned_loss_pct"] == pytest.approx(3.0)
    assert row["dollar_risk"] == pytest.approx(-1.5)        # -1R at a 3% stop = 1.5 x the 2% cap
    assert row["expiry_bars"] == 4 and row["source"] == "short_lane"


def test_a_no_qualifying_target_record_is_a_no_plan_row():
    (row,) = gci.live_blocked_rows([_record(gate="plan_rejected", reason="no_qualifying_target",
                                            margin=None, cf_status="no-plan", cf_r=None, win=None)])
    assert (row["cf_status"], row["cf_r"], row["planned_loss_pct"], row["dollar_risk"]) == \
        ("no-plan", None, None, None)


# --- live taken -----------------------------------------------------------------

def test_a_taken_plan_is_walked_by_the_replays_exact_call_and_copied_per_gate():
    bars, plan = _bars(), _plan()
    rows = gci.live_taken_rows([plan], lambda ticker: bars, realised={"p1": 0.7})
    assert [r["gate"] for r in rows] == ["rs", "plan_rejected"]
    expected = simulate_exit(bars, 2, plan, scale_out=True)
    for row in rows:
        assert (row["arm"], row["population"], row["reason"]) == ("taken", "live", None)
        assert row["cf_status"] == "filled" and row["win"] is True
        assert row["cf_r"] == pytest.approx(expected.r_total)
        assert row["realised_r"] == 0.7 and row["signal_date"] == "2024-01-04"


def test_a_compression_plan_is_in_the_rs_and_compression_taken_arms():
    plan = _plan(source="strategy", strategy=COMPRESSION_SHORT, direction="bearish",
                 stop_loss=105.0, tp1=98.0, tp2=95.0)
    rows = gci.live_taken_rows([plan], lambda ticker: _bars())
    assert [r["gate"] for r in rows] == ["rs", "compression"]
    assert rows[0]["realised_r"] is None


@pytest.mark.parametrize("change", [{"origin": "next_session"}, {"ticker": "XAUUSD"}])
def test_outlook_plans_and_spot_metals_are_out(change):
    assert gci.live_taken_rows([_plan(**change)], lambda ticker: _bars()) == []


def test_a_walk_still_waiting_for_bars_is_skipped():
    assert gci.live_taken_rows([_plan()], lambda ticker: _bars(n_after=5)) == []


def test_missing_bars_are_a_no_data_row():
    rows = gci.live_taken_rows([_plan()], lambda ticker: None)
    assert {r["cf_status"] for r in rows} == {"no-data"}


def test_bars_are_loaded_once_per_ticker():
    calls = []

    def load(ticker):
        calls.append(ticker)
        return _bars()

    gci.live_taken_rows([_plan(plan_id="a"), _plan(plan_id="b")], load)
    assert calls == ["AAPL"]


def test_the_last_completed_session_bounds_the_walk():
    # the bar dated 2024-01-05 is the TP1 bar; a cut at 2024-01-04 leaves the walk pending
    assert gci.live_taken_rows([_plan()], lambda t: _bars(), last_session="2024-01-04") == []


def test_realised_r_comes_from_closed_trades_only():
    trades = [{"plan_id": "p1", "status": "closed", "entry": 100.0, "stop_loss": 95.0,
               "direction": "bullish", "exit_price": 105.0, "legs": []},
              {"plan_id": "p2", "status": "open", "entry": 100.0, "stop_loss": 95.0,
               "direction": "bullish", "exit_price": None, "legs": []},
              {"plan_id": None, "status": "closed", "entry": 100.0, "stop_loss": 95.0,
               "direction": "bullish", "exit_price": 90.0, "legs": []}]
    assert gci.realised_r_by_plan(trades) == {"p1": pytest.approx(1.0)}


@pytest.mark.parametrize("moment, expected", [
    (dt.datetime(2024, 1, 10, 15, 0), "2024-01-09"),     # Wednesday, session still open
    (dt.datetime(2024, 1, 10, 16, 30), "2024-01-10"),    # after the close
    (dt.datetime(2024, 1, 13, 12, 0), "2024-01-12"),     # Saturday
    (dt.datetime(2024, 1, 16, 10, 0), "2024-01-12"),     # Tuesday after the MLK holiday
])
def test_last_completed_session(moment, expected):
    assert gci.last_completed_session(moment.replace(tzinfo=US_MARKET_TZ)) == expected


def test_load_live_reads_the_table_and_the_plans_since_the_window(monkeypatch):
    from swingbot.core.db.repositories import gate_rejections
    from swingbot.core.marketdata import data_store
    from swingbot.core.planning import plan_store

    seen = {}

    class _Repo:
        def list_since(self, since=None, *, conn=None):
            seen["since"] = since
            return [_record()]

    class _Store:
        def all(self):
            return [_plan(plan_id="old", created_at="2026-09-30"), _plan(plan_id="new", created_at="2026-10-02")]

    def _load(ticker, interval):
        seen.setdefault("loads", []).append((ticker, interval))
        return None

    monkeypatch.setattr(gate_rejections, "gate_rejections_repo", lambda: _Repo())
    monkeypatch.setattr(plan_store, "PlanStore", _Store)
    monkeypatch.setattr(data_store, "load_normalized", _load)
    monkeypatch.setattr(gci, "realised_r_by_plan", lambda trades=None: {})
    blocked, taken = gci.load_live(now=dt.datetime(2026, 10, 9, 22, 0, tzinfo=dt.timezone.utc))
    assert seen["since"] == "2026-10-01" and seen["loads"] == [("AAPL", "daily")]
    assert len(blocked) == 1 and {r["signal_date"] for r in taken} == {"2026-10-02"}
