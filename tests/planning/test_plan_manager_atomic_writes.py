"""V189-8: the TP1 leg and the fill commit in the plan's own transaction, a
refused stale write aborts the step with nothing emitted, and the close hooks
run only after the close has committed."""
from __future__ import annotations

import datetime as dt
import logging
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.db.engine import BOT_LOCK_TIMEOUT_MS
from swingbot.core.db.repositories.account import account_repo
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import (PlanEvent, PlanManager, PlanPersistFailed,
                                                 PlanWriteAborted)
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active
from tests.planning.test_plan_manager_pending import _pending
from tests.store_seed import seed_store

SATURDAY = dt.datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
MANAGER_LOG = "swingbot.core.planning.plan_manager"
STORE_LOG = "swingbot.core.planning.plan_store"


@pytest.fixture
def trade_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def _open_trade(trade_log, *, entry=100.0, stop_loss=95.0) -> str:
    return trade_log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=None, confidence_label=None, entry=entry, stop_loss=stop_loss,
        take_profit=110.0, target2=120.0, plan_id="p1")


def _manager(trade_log, prices, plan):
    store = PlanStore()
    store.add(plan)
    feed = FakePriceFeed([("AAPL", p) for p in prices])
    return store, PlanManager(store, feed.get_price, trade_log=trade_log)


def _transitions(events, name):
    return [e for e in events if e.transition == name]


def _end_elsewhere(status: str) -> None:
    """Another process ends the plan between the bot's read and its write."""
    other = PlanStore()
    plan = other.get("p1")
    if status == PlanStatus.CLOSED:
        record_transition(plan, PlanStatus.CLOSED, reason="manual", at="t1")
    else:
        plan.status = status          # a direct row write, as another process leaves it
    assert other.update(plan) is True


def _refuse(*_args, **_kwargs):
    raise RuntimeError("trades table unavailable")


# --- the lock timeout of the bot path ------------------------------------------------

def test_the_manager_puts_its_store_on_the_bot_lock_timeout():
    store = PlanStore()
    PlanManager(store, lambda ticker: 100.0)
    assert store.lock_timeout_ms == BOT_LOCK_TIMEOUT_MS


def test_a_store_double_without_a_timeout_is_left_alone():
    store = object()
    PlanManager(store, lambda ticker: 100.0)
    assert not hasattr(store, "lock_timeout_ms")


def test_save_tolerates_a_store_double_that_returns_nothing():
    class _NoneStore:
        def update(self, plan, **_kw):
            return None

    PlanManager(_NoneStore(), lambda ticker: 100.0)._save(_active())   # no raise


def test_save_raises_when_the_store_refuses():
    class _RefusingStore:
        def update(self, plan, **_kw):
            return False

    with pytest.raises(PlanWriteAborted) as info:
        PlanManager(_RefusingStore(), lambda ticker: 100.0)._save(_active())
    assert info.value.plan_id == "p1"


# --- TP1 leg -----------------------------------------------------------------------

def test_the_tp1_leg_commits_with_the_partial_transition(trade_log):
    _open_trade(trade_log)
    store, mgr = _manager(trade_log, [110.0], _active(tp2=120.0))

    events = mgr.poll(now=SATURDAY)

    assert [e.transition for e in events] == ["tp1_partial"]
    plan = store.get("p1")
    assert plan.status == PlanStatus.PARTIAL and len(plan.legs_realized) == 1
    trade = trade_log.trade_for_plan("p1")
    assert trade["legs"] == [plan.legs_realized[0]]
    assert trade["legs"][0]["reason"] == "tp1" and trade["legs"][0]["r"] == pytest.approx(2.0)


def test_a_failed_tp1_leg_rolls_the_partial_back(trade_log, monkeypatch, caplog):
    _open_trade(trade_log)
    store, mgr = _manager(trade_log, [110.0], _active(tp2=120.0))
    monkeypatch.setattr(trade_log, "append_leg_by_plan", _refuse)
    caplog.set_level(logging.ERROR, logger=MANAGER_LOG)

    assert mgr.poll(now=SATURDAY) == []

    plan = store.get("p1")
    assert plan.status == PlanStatus.ACTIVE
    assert plan.legs_realized == [] and plan.working_stop is None
    assert not trade_log.trade_for_plan("p1").get("legs")
    assert "p1" in caplog.text and "transaction rolled back" in caplog.text


# --- fill ---------------------------------------------------------------------------

def test_the_fill_commits_with_the_active_transition(trade_log):
    trade_id = _open_trade(trade_log, entry=105.0, stop_loss=104.0)
    store, mgr = _manager(trade_log, [106.0], _pending(stop_loss=104.0))

    filled = _transitions(mgr.poll(now=SATURDAY), "filled")

    assert len(filled) == 1 and filled[0].detail["trade_id"] == trade_id
    assert store.get("p1").status == PlanStatus.ACTIVE
    assert trade_log.trade_for_plan("p1")["entry"] == 106.0


def test_a_failed_fill_leaves_the_plan_pending_and_the_placeholder_untouched(
        trade_log, monkeypatch, caplog):
    _open_trade(trade_log, entry=105.0, stop_loss=104.0)
    store, mgr = _manager(trade_log, [106.0], _pending(stop_loss=104.0))
    monkeypatch.setattr(trade_log, "record_plan_fill", _refuse)
    caplog.set_level(logging.ERROR, logger=MANAGER_LOG)

    assert _transitions(mgr.poll(now=SATURDAY), "filled") == []
    assert store.get("p1").status == PlanStatus.PENDING
    assert trade_log.trade_for_plan("p1")["entry"] == 105.0
    assert "transaction rolled back" in caplog.text


def test_a_fill_without_a_placeholder_still_logs_a_trade_through_on_event(trade_log):
    store, mgr = _manager(trade_log, [106.0], _pending(stop_loss=104.0))
    filled = _transitions(mgr.poll(now=SATURDAY), "filled")
    assert filled[0].detail.get("trade_id") is not None
    assert trade_log.trade_for_plan("p1")["entry"] == 106.0


# --- _on_event no longer writes legs or fills ------------------------------------------

def test_on_event_writes_no_leg_and_no_fill():
    log = MagicMock()
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0, trade_log=log)
    plan = _active()

    mgr._on_event(plan, PlanEvent("p1", "tp1_partial", {"fraction": 0.5, "exit_price": 110.0}))
    mgr._on_event(plan, PlanEvent("p1", "filled", {"entry_price": 100.0, "trade_id": "T9"}))

    log.append_leg_by_plan.assert_not_called()
    log.record_plan_fill.assert_not_called()
    log.log_trade.assert_not_called()


def test_on_event_falls_back_to_log_trade_only_without_a_trade_id():
    log = MagicMock()
    log.log_trade.return_value = "T-NEW"
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0, trade_log=log)
    event = PlanEvent("p1", "filled", {"entry_price": 100.0})

    mgr._on_event(_active(), event)

    log.log_trade.assert_called_once()
    assert event.detail["trade_id"] == "T-NEW"


# --- aborts emit nothing ----------------------------------------------------------------

def test_an_exit_over_a_plan_ended_elsewhere_aborts_and_emits_nothing(
        trade_log, monkeypatch, caplog):
    _open_trade(trade_log)
    store, mgr = _manager(trade_log, [94.0], _active(tp2=120.0))
    hooks: list = []
    monkeypatch.setattr(performance, "_after_close", lambda trade: hooks.append("journal"))

    def cancelled_meanwhile(plan, stop, now):
        _end_elsewhere(PlanStatus.CANCELLED)
        return False

    monkeypatch.setattr(mgr, "_continuous", cancelled_meanwhile)
    history_before = len(account_repo().history())
    caplog.set_level(logging.INFO, logger=STORE_LOG)

    assert mgr.poll(now=SATURDAY) == []

    assert store.get("p1").status == PlanStatus.CANCELLED
    assert trade_log.trade_for_plan("p1")["status"] == "open"
    assert len(account_repo().history()) == history_before
    assert hooks == []
    assert "refused stale write to p1" in caplog.text


def test_a_stale_non_status_write_aborts_the_step(trade_log, monkeypatch):
    store, mgr = _manager(trade_log, [105.0], _active(tp2=120.0))
    real_trigger = plan_manager.breakeven_trigger

    def closed_meanwhile(plan, entry):
        _end_elsewhere(PlanStatus.CLOSED)
        return real_trigger(plan, entry)

    monkeypatch.setattr(plan_manager, "breakeven_trigger", closed_meanwhile)

    assert mgr.poll(now=SATURDAY) == []
    stored = store.get("p1")
    assert stored.status == PlanStatus.CLOSED and stored.working_stop is None


def test_check_bar_returns_nothing_when_the_write_is_refused(trade_log, monkeypatch):
    store, mgr = _manager(trade_log, [], _active(tp2=120.0))

    def refused(plan, *, conn=None):
        raise PlanWriteAborted(plan.plan_id)

    monkeypatch.setattr(mgr, "_save", refused)
    assert mgr.check_bar("p1", 111.0, 112.0, 109.0) == []


def test_check_bar_returns_nothing_when_the_write_rolled_back(trade_log, monkeypatch):
    store, mgr = _manager(trade_log, [], _active(tp2=120.0))

    def failed(plan, leg):
        raise PlanPersistFailed(plan.plan_id)

    monkeypatch.setattr(mgr, "_persist_partial", failed)
    assert mgr.check_bar("p1", 111.0, 112.0, 109.0) == []


# --- hooks after commit -------------------------------------------------------------

def test_close_hooks_see_the_committed_close(trade_log, monkeypatch):
    _open_trade(trade_log)
    store, mgr = _manager(trade_log, [94.0], _active(tp2=120.0))
    seen: list = []

    def journal(trade):
        # A fresh connection: it sees only what has committed.
        seen.append((PlanStore().get("p1").status, TradeLog().trade_for_plan("p1")["status"]))

    monkeypatch.setattr(performance, "_after_close", journal)

    assert [e.transition for e in mgr.poll(now=SATURDAY)] == ["closed"]
    assert seen == [(PlanStatus.CLOSED, "loss")]


def test_a_terminal_close_reaches_the_trade_with_its_close_reason(trade_log):
    _open_trade(trade_log)
    store, mgr = _manager(trade_log, [], _active(tp2=120.0))
    plan = store.get("p1")
    record_transition(plan, PlanStatus.CLOSED, reason="scratch", at="t1")
    leg = {"fraction": 1.0, "exit_price": 100.0, "r": 0.0, "reason": "scratch"}

    assert mgr._persist_terminal(plan, leg, "closed", close_reason="scratch") is True

    trade = trade_log.trade_for_plan("p1")
    assert (trade["status"], trade["close_reason"]) == ("closed", "scratch")
    assert store.get("p1").status == PlanStatus.CLOSED
