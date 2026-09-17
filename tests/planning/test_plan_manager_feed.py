"""v81 execution-feed bookkeeping: stop delivery state and terminal notices."""
import datetime as dt
from unittest.mock import patch

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_engine import PlanStatus, runner_floor
from swingbot.core.planning.plan_manager import (PlanManager, resting_stop,
                                                 stop_move_event, trail_notify_min_r)
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
from tests.planning.test_plan_manager_pending import _pending


DAY = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def _pinned_flags(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "EXTENDED_HOURS_EXIT_CHECK", True)
    monkeypatch.setattr(config, "TRAIL_NOTIFY_MIN_R", 0.25)
    monkeypatch.setattr(config, "PYRAMIDING_ENABLED", False)


def _env(tmp_path, prices, plan=None, atr_fn=None):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(plan if plan is not None else _active())
    return store, PlanManager(store, feed.get_price, atr_fn=atr_fn)


def _runner(working_stop, notified_stop=None):
    return _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 tp2=None, working_stop=working_stop, notified_stop=notified_stop)


def test_threshold_is_clamped(monkeypatch):
    monkeypatch.setattr(config, "TRAIL_NOTIFY_MIN_R", 3.0)
    assert trail_notify_min_r() == 1.0
    monkeypatch.setattr(config, "TRAIL_NOTIFY_MIN_R", 0.0)
    assert trail_notify_min_r() == 0.01


def test_stop_move_has_resting_stop_and_is_effective_now():
    # A moved stop is live the instant it moves -- no same-session delay.
    plan = _plan(status="ACTIVE", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=100.0, be_armed_session="2026-08-27")
    event = stop_move_event(plan, "2026-08-27", 0.25)
    assert event.detail == {"old": 95.0, "new": 100.0, "r_moved": pytest.approx(1.0),
                            "effective": "now"}
    assert resting_stop(_runner(None)) == pytest.approx(runner_floor(100.0, 110.0))


def test_pending_plan_never_emits_stop_move():
    assert stop_move_event(_pending(), "2026-08-27", 0.25) is None


def test_break_even_is_resent_as_stop_move_until_acknowledged(tmp_path):
    store, manager = _env(tmp_path, [105.0, 105.0, 105.0])
    assert [e.transition for e in manager.poll(now=DAY)] == ["be_moved"]
    events = manager.poll(now=DAY)
    assert [e.transition for e in events] == ["stop_moved"]
    plan = store.get("p1")
    plan.notified_stop = 100.0
    store.update(plan)
    assert manager.poll(now=DAY) == []


def test_closed_event_is_stamped_queued_and_resent(tmp_path):
    store, manager = _env(tmp_path, [94.5])
    event = manager.poll(now=DAY)[0]
    assert event.transition == "closed"
    assert event.detail["session"] == "regular"
    assert event.detail["notified_stop"] == event.detail["bot_stop"] == 95.0
    assert store.get("p1").pending_notice["transition"] == "closed"
    assert [e.transition for e in manager.poll(now=DAY)] == ["closed"]


def test_tp1_event_carries_runner_stop(tmp_path):
    _, manager = _env(tmp_path, [110.5], plan=_active(tp2=None))
    event = manager.poll(now=DAY)[0]
    assert event.transition == "tp1_partial"
    assert event.detail["working_stop"] == pytest.approx(runner_floor(100.0, 110.0))


def test_stale_notice_is_dropped(tmp_path, caplog):
    stale = _plan(status="CLOSED", pending_notice={
        "transition": "closed", "detail": {"reason": "loss", "exit_price": 94.5},
        "at": "2000-01-01T00:00:00+00:00"})
    store, manager = _env(tmp_path, [], plan=stale)
    from swingbot.core.planning import plan_manager as manager_mod
    with patch.object(manager_mod.log, "warning") as warning:
        assert manager.poll(now=DAY) == []
    assert store.get("p1").pending_notice is None
    assert "dropping undelivered" in str(warning.call_args)
    assert "closed" in str(warning.call_args)
