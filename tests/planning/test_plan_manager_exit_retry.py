"""V189-9: a failed exit is retried once with the same observed price; a second
failure is logged, recorded and posted to the ops channel. Aborts and non-exit
writes are never retried."""
from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import logging
import time
import types
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.account import account_repo
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active
from tests.store_seed import seed_store

SATURDAY = dt.datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
MANAGER_LOG = "swingbot.core.planning.plan_manager"


@pytest.fixture
def trade_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    log = TradeLog()
    log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=None, confidence_label=None, entry=100.0, stop_loss=95.0,
        take_profit=110.0, target2=120.0, plan_id="p1")
    return log


def _manager(trade_log, prices):
    store = PlanStore()
    store.add(_active(tp2=120.0))
    feed = FakePriceFeed([("AAPL", p) for p in prices])
    return store, PlanManager(store, feed.get_price, trade_log=trade_log)


def _spy_close(trade_log, monkeypatch, *, fail_times: int) -> list:
    """Wrap close_plan_trade: record every call's leg, fail the first ``fail_times``."""
    real = trade_log.close_plan_trade
    calls: list = []

    def close(plan_id, leg, status, **kwargs):
        calls.append(dict(leg))
        if len(calls) <= fail_times:
            raise RuntimeError("trades table unavailable")
        return real(plan_id, leg, status, **kwargs)

    monkeypatch.setattr(trade_log, "close_plan_trade", close)
    return calls


# --- _step_safely: which skips count as check errors --------------------------------

def _raising_step(monkeypatch, mgr, exc):
    def step(plan, price, now):
        raise exc
    monkeypatch.setattr(mgr, "_step", step)


def test_a_locked_plan_is_skipped_without_a_check_error(monkeypatch):
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0)
    _raising_step(monkeypatch, mgr, plan_manager.LockTimeout("row locked"))
    assert mgr._step_safely(_active(), 100.0, SATURDAY) is None
    assert mgr.last_poll_check_errors == []


@pytest.mark.parametrize("exc", [RuntimeError("boom"), plan_manager.PlanPersistFailed("p1")],
                         ids=["unexpected", "persist_failed"])
def test_a_failed_step_is_recorded_as_a_check_error(monkeypatch, exc):
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0)
    _raising_step(monkeypatch, mgr, exc)
    assert mgr._step_safely(_active(), 100.0, SATURDAY) is None
    assert mgr.last_poll_check_errors == ["AAPL"]


# --- retry once ------------------------------------------------------------------------

def test_a_failed_exit_is_retried_once_with_the_same_price(trade_log, monkeypatch, caplog):
    store, mgr = _manager(trade_log, [94.0])
    calls = _spy_close(trade_log, monkeypatch, fail_times=1)
    history_before = len(account_repo().history())
    caplog.set_level(logging.WARNING, logger=MANAGER_LOG)

    events = mgr.poll(now=SATURDAY)

    assert [e.transition for e in events] == ["closed"]
    assert len(calls) == 2 and calls[0] == calls[1]
    assert calls[0]["exit_price"] == 94.0
    assert store.get("p1").status == PlanStatus.CLOSED
    trade = trade_log.trade_for_plan("p1")
    assert trade["status"] == "loss" and trade["exit_price"] == 94.0
    assert len(account_repo().history()) == history_before + 1   # one point, not two
    assert mgr.take_exit_failures() == []
    assert "retrying once" in caplog.text


def test_an_exit_that_fails_twice_is_recorded_and_emits_nothing(trade_log, monkeypatch, caplog):
    store, mgr = _manager(trade_log, [94.0])
    calls = _spy_close(trade_log, monkeypatch, fail_times=2)
    history_before = len(account_repo().history())
    caplog.set_level(logging.ERROR, logger=MANAGER_LOG)

    assert mgr.poll(now=SATURDAY) == []

    assert len(calls) == 2
    assert store.get("p1").status == PlanStatus.ACTIVE
    assert trade_log.trade_for_plan("p1")["status"] == "open"
    assert len(account_repo().history()) == history_before
    assert mgr.take_exit_failures() == [{
        "plan_id": "p1", "ticker": "AAPL", "exit_price": 94.0, "reason": "loss",
        "error": "RuntimeError: trades table unavailable"}]
    assert mgr.take_exit_failures() == []                 # drained
    assert "exit not recorded" in caplog.text and "p1" in caplog.text


def test_an_aborted_exit_is_not_retried(trade_log, monkeypatch):
    store, mgr = _manager(trade_log, [94.0])
    calls = _spy_close(trade_log, monkeypatch, fail_times=0)

    def cancelled_meanwhile(plan, stop, now):
        other = PlanStore()
        stored = other.get("p1")
        stored.status = PlanStatus.CANCELLED
        other.update(stored)
        return False

    monkeypatch.setattr(mgr, "_continuous", cancelled_meanwhile)

    assert mgr.poll(now=SATURDAY) == []
    assert calls == []
    assert mgr.take_exit_failures() == []


def test_a_failed_tp1_leg_is_not_retried(trade_log, monkeypatch):
    store, mgr = _manager(trade_log, [110.0])
    attempts: list = []

    def refuse(*_args, **_kwargs):
        attempts.append(1)
        raise RuntimeError("trades table unavailable")

    monkeypatch.setattr(trade_log, "append_leg_by_plan", refuse)

    assert mgr.poll(now=SATURDAY) == []
    assert attempts == [1]
    assert mgr.take_exit_failures() == []


@pytest.mark.slow
def test_an_exit_whose_plan_row_stays_locked_is_retried_then_reported(trade_log):
    store, mgr = _manager(trade_log, [94.0])
    with transaction() as conn:
        PlanStore().lock_for_update("p1", conn=conn)       # another process holds the row
        started = time.monotonic()
        events = mgr.poll(now=SATURDAY)
        elapsed = time.monotonic() - started

    assert events == []
    assert 1.5 < elapsed < 6.0                             # two 1s lock waits
    [failure] = mgr.take_exit_failures()
    assert failure["plan_id"] == "p1" and failure["error"].startswith("LockTimeout")
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_drain_exit_failures_before_the_first_tick_is_empty(monkeypatch):
    monkeypatch.setattr(plan_manager, "_MANAGER", None)
    assert plan_manager.drain_exit_failures() == []


def test_drain_exit_failures_empties_the_process_manager(monkeypatch):
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0)
    mgr._exit_failures.append({"plan_id": "p1"})
    monkeypatch.setattr(plan_manager, "_MANAGER", mgr)
    assert plan_manager.drain_exit_failures() == [{"plan_id": "p1"}]
    assert plan_manager.drain_exit_failures() == []


# --- the ops-channel notice ---------------------------------------------------------------

class _Channel:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord is having a day")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=1)


FAILURE = {"plan_id": "p1", "ticker": "AAPL", "exit_price": 94.0, "reason": "loss",
           "error": "RuntimeError: boom"}


def test_each_failed_exit_posts_one_ops_line(monkeypatch):
    chan = _Channel()
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: chan)
    second = {**FAILURE, "plan_id": "p2", "ticker": "MSFT", "exit_price": 310.5,
              "reason": "tp1_runner_trail"}

    asyncio.run(loops_mod._post_exit_failures([FAILURE, second]))

    assert [m["content"] for m in chan.sent] == [
        "⚠️ Exit not recorded: AAPL plan `p1` -- observed loss exit at 94.00. "
        "The book still shows the position open; check it by hand.",
        "⚠️ Exit not recorded: MSFT plan `p2` -- observed tp1_runner_trail exit at 310.50. "
        "The book still shows the position open; check it by hand.",
    ]


def test_no_failures_look_up_no_channel(monkeypatch):
    looked_up: list = []
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: looked_up.append(1))
    asyncio.run(loops_mod._post_exit_failures([]))
    assert looked_up == []


def test_without_a_channel_the_failure_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: None)
    with caplog.at_level(logging.ERROR):
        asyncio.run(loops_mod._post_exit_failures([FAILURE]))
    assert any("no ops channel" in r.getMessage() for r in caplog.records)


def test_a_failing_send_warns_and_keeps_posting(monkeypatch, caplog):
    chan = _Channel(fail=True)
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: chan)
    with caplog.at_level(logging.WARNING):
        asyncio.run(loops_mod._post_exit_failures([FAILURE, {**FAILURE, "plan_id": "p2"}]))
    messages = [r.getMessage() for r in caplog.records]
    assert sum("exit-failure notice" in m for m in messages) == 2


def test_trade_monitor_posts_the_drained_failures_after_the_manager_tick():
    # trade_monitor's body lives in _monitor_tick (v184); the manager tick
    # runs through _run_plan_manager_tick.
    source = inspect.getsource(loops_mod._monitor_tick)
    tick = source.index("await _run_plan_manager_tick()")
    post = source.index("await _post_exit_failures(plan_manager.drain_exit_failures())")
    assert tick < post
