"""One plan is one position -- never two trades.

Two paths log trades and only one of them dedups. The scan writes the
candidate's trade the moment it alerts (`scanning/engine.py`, guarded by
`already_open`); PlanManager then logs a brand-new trade on the plan's
`filled` transition with no check at all. A plan alerted as PENDING and
filled minutes later therefore got two trades, double-booking the risk --
and when the plan later went terminal, `close_plan_trade` closed only the
first, leaving the second open against a plan nobody polls (see
tests/test_unowned_target_close.py).

Live as of 2026-08-04: 13 of 372 plans carry two trades. AVGO plan
`47def9d0` has them 8 minutes apart -- 19:17:11 (scan) and 19:25:22 (fill).
"""
import json

import pytest

from swingbot import config
from swingbot.core.performance import TradeLog
from swingbot.core.plan_engine import PlanStatus
from swingbot.core.plan_manager import PlanManager
from swingbot.core.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.test_plan_manager_pending import _pending


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(
        "swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    store = PlanStore(path=str(tmp_path / "plans.json"))
    monkeypatch.setattr("swingbot.core.plan_store.PlanStore",
                        lambda *a, **k: store)

    def _make(trades):
        path = tmp_path / "trades.json"
        path.write_text(json.dumps(trades))
        return TradeLog(path=str(path)), store

    return _make


def _scan_trade(plan_id):
    """What scanning/engine.py writes when it alerts the candidate."""
    return {"id": "scan1", "ticker": "AAPL", "direction": "bullish",
            "status": "open", "entry": 105.0, "stop_loss": 95.0,
            "take_profit": 110.0, "plan_id": plan_id,
            "opened_at": "2026-07-01T10:00:00+00:00"}


def _fill(log, store, trades):
    """Run one manager tick that fills the PENDING plan."""
    plan = _pending(plan_id="p1", tp1=110.0, tp2=125.0)
    store.add(plan)
    feed = FakePriceFeed()
    feed.set_series("AAPL", [106.0])          # crosses the 105 trigger
    mgr = PlanManager(store, feed.get_price, atr_fn=lambda t: 2.0, trade_log=log)
    return mgr.poll()


def test_fill_does_not_log_a_second_trade_for_the_same_plan(env):
    log, store = env([_scan_trade("p1")])

    events = _fill(log, store, [_scan_trade("p1")])

    assert [e.transition for e in events] == ["filled"]
    open_for_plan = [t for t in log.get_trades(status="open", limit=50)
                     if t.get("plan_id") == "p1"]
    assert len(open_for_plan) == 1
    assert open_for_plan[0]["id"] == "scan1"   # the scan's trade, not a new one


def test_fill_still_logs_a_trade_when_the_scan_did_not(env):
    """The manager is the only writer for a plan the scan never booked --
    that path must keep working."""
    log, store = env([])

    events = _fill(log, store, [])

    assert [e.transition for e in events] == ["filled"]
    open_for_plan = [t for t in log.get_trades(status="open", limit=50)
                     if t.get("plan_id") == "p1"]
    assert len(open_for_plan) == 1


def test_a_closed_trade_does_not_block_a_new_fill(env):
    """Only OPEN trades count -- a plan whose earlier trade already closed
    must still be able to book the next one."""
    done = _scan_trade("p1")
    done.update(status="win", exit_price=110.0)
    log, store = env([done])

    _fill(log, store, [done])

    assert len([t for t in log.get_trades(status="open", limit=50)
                if t.get("plan_id") == "p1"]) == 1


def test_has_open_trade_for_plan_ignores_other_plans(env):
    log, _ = env([_scan_trade("other")])
    assert log.has_open_trade_for_plan("p1") is False
    assert log.has_open_trade_for_plan("other") is True
