"""V189-10: a runner or time-exit close after TP1 is labelled by the sign of
its unrounded net R (metrics.net_outcome) -- the golden partial trade end to
end, and the D2 label table on both plan-manager close paths. Single-leg
closes keep their labels."""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.analytics import metrics
from swingbot.core.planning import time_exit as te
from swingbot.core.planning.plan_engine import PlanStatus, record_transition, runner_floor
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

SATURDAY = dt.datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
AUCTION_ASOF = "2026-10-16T20:00:05+00:00"
GOLDEN = json.loads((Path(__file__).resolve().parents[1] / "analytics"
                     / "golden_partial_trade.json").read_text(encoding="utf-8"))
G = GOLDEN["trade"]
CASES = {case["name"]: case for case in GOLDEN["closed_cases"]}
LABELS = [(row["net_r"], row["status"], row["close_reason"]) for row in GOLDEN["label_table"]]


@pytest.fixture
def trade_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    log = TradeLog()
    log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction=G["direction"],
        confidence_level=None, confidence_label=None, entry=G["entry"],
        stop_loss=G["stop_loss"], take_profit=G["tp1"], target2=G["tp2"], plan_id="p1")
    return log


def _golden_plan():
    plan = _plan(entry_type="market", direction=G["direction"], trigger_price=G["entry"],
                 entry_price=G["entry"], stop_loss=G["stop_loss"], tp1=G["tp1"],
                 tp2=G["tp2"], tp1_fraction=G["tp1_fraction"])
    record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    return plan


def _manager(trade_log, prices):
    store = PlanStore()
    store.add(_golden_plan())
    feed = FakePriceFeed([("AAPL", p) for p in prices])
    return store, PlanManager(store, feed.get_price, trade_log=trade_log)


def _after_tp1(trade_log, runner_prices):
    """TP1 banked at exactly 110 (+2R on half), then ``runner_prices`` queued."""
    store, mgr = _manager(trade_log, [G["tp1"], *runner_prices])
    assert [e.transition for e in mgr.poll(now=SATURDAY)] == ["tp1_partial"]
    return store, mgr


def _runner_close(trade_log, exit_price) -> dict:
    """The live poll path: the runner's stop is hit and fills at the print."""
    store, mgr = _after_tp1(trade_log, [exit_price])
    closed = [e for e in mgr.poll(now=SATURDAY) if e.transition == "closed"]
    assert len(closed) == 1
    assert store.get("p1").status == PlanStatus.CLOSED
    return trade_log.trade_for_plan("p1")


def _time_exit_close(trade_log, exit_price) -> dict:
    """The time-exit path on a scaled-out plan, at the official auction price."""
    store, mgr = _after_tp1(trade_log, [])
    auction = te.AuctionClose(exit_price, te.OFFICIAL_BASIS, AUCTION_ASOF)
    events = mgr._close_time_exit(store.get("p1"), auction)
    assert [e.transition for e in events] == ["closed"]
    return trade_log.trade_for_plan("p1")


def _runner_exit_for(net_r: float) -> float:
    """The runner exit that nets ``net_r`` after the golden TP1 leg."""
    fraction, r1 = G["tp1_fraction"], G["tp1_leg"]["r"]
    runner_r = (net_r - fraction * r1) / (1 - fraction)
    return G["entry"] + runner_r * G["risk_per_share"]


def _assert_golden(record: dict, case: dict) -> None:
    assert (record["status"], record.get("close_reason")) == (case["status"], case["close_reason"])
    assert len(record["legs"]) == 2
    assert metrics.r_multiple(record) == pytest.approx(case["net_r"], abs=GOLDEN["tolerance"])
    per_share = case["realized_pnl_amount"] / G["shares"]
    assert record["realized_pnl_amount"] == pytest.approx(record["shares"] * per_share, abs=0.02)


# --- the golden partial trade ---------------------------------------------------------

def test_golden_floor_close_is_a_win(trade_log):
    floor = runner_floor(G["entry"], G["tp1"])
    assert floor == pytest.approx(CASES["floor"]["runner_exit"])
    record = _runner_close(trade_log, floor)
    assert record["legs"][-1]["reason"] == "tp1_runner_be"
    _assert_golden(record, CASES["floor"])


def test_golden_gap_below_the_original_stop_is_a_loss(trade_log):
    record = _runner_close(trade_log, CASES["gap"]["runner_exit"])
    _assert_golden(record, CASES["gap"])          # TP1 was touched; the net is -0.20R


def test_golden_time_exit_after_tp1_is_a_win(trade_log):
    record = _time_exit_close(trade_log, CASES["time_exit"]["runner_exit"])
    assert record["legs"][-1]["reason"] == te.TIME_EXIT_REASON
    _assert_golden(record, CASES["time_exit"])    # was "closed" before v189


# --- the D2 label table on both plan-manager close paths --------------------------------

@pytest.mark.parametrize("close", [_runner_close, _time_exit_close], ids=["runner", "time_exit"])
@pytest.mark.parametrize("net_r, status, close_reason", LABELS,
                         ids=[f"net{row[0]:+}" for row in LABELS])
def test_the_label_follows_the_net_r_sign(trade_log, close, net_r, status, close_reason):
    record = close(trade_log, _runner_exit_for(net_r))
    assert (record["status"], record.get("close_reason")) == (status, close_reason)
    assert metrics.r_multiple(record) == pytest.approx(net_r, abs=GOLDEN["tolerance"])


# --- single-leg closes keep today's labels ----------------------------------------------

def test_a_pre_tp1_stop_is_still_a_loss(trade_log):
    store, mgr = _manager(trade_log, [94.0])
    assert [e.transition for e in mgr.poll(now=SATURDAY)] == ["closed"]
    record = trade_log.trade_for_plan("p1")
    assert (record["status"], record.get("close_reason")) == ("loss", None)


def test_a_single_leg_time_exit_keeps_its_closed_label(trade_log):
    store, mgr = _manager(trade_log, [])
    auction = te.AuctionClose(101.0, te.OFFICIAL_BASIS, AUCTION_ASOF)
    events = mgr._close_time_exit(store.get("p1"), auction)
    assert [e.transition for e in events] == ["closed"]
    record = trade_log.trade_for_plan("p1")
    assert (record["status"], record.get("close_reason")) == ("closed", None)


# --- the outcome helper -------------------------------------------------------------------

def _scaled_out(**kw):
    plan = _golden_plan()
    plan.legs_realized = [dict(G["tp1_leg"]), {"fraction": 0.5, "exit_price": 115.0,
                                               "r": 3.0, "reason": "manual"}]
    for key, value in kw.items():
        setattr(plan, key, value)
    return plan


def test_plan_outcome_labels_a_scaled_out_plan_by_net_r():
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0)
    assert mgr._plan_outcome(_scaled_out()) == ("win", None)          # net +2.5R


def test_a_nan_leg_is_unscored_with_a_warning(caplog):
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0)
    plan = _scaled_out()
    plan.legs_realized[1] = {"fraction": 0.5, "exit_price": math.nan, "r": math.nan,
                             "reason": "manual"}
    caplog.set_level(logging.WARNING)
    assert mgr._plan_outcome(plan) == ("closed", "unscored")
    assert "p1" in caplog.text


def test_a_plan_with_no_risk_basis_is_unscored():
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0)
    assert mgr._plan_outcome(_scaled_out(stop_loss=G["entry"])) == ("closed", "unscored")
