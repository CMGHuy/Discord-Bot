"""v152 D1: the R-based near-stop PlanEvent.

ACTIVE/PARTIAL only, regular session only, never beyond the resting stop,
within 0.25 initial R of it. poll() gains one statement for it; the
execution feed (notify_plan_events) never posts it -- it is follow-only.
"""
import asyncio
import datetime as dt
import types

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import (FOLLOW_ONLY_EVENTS, NEAR_STOP_R, NOTICE_EVENTS,
                                                 STOP_EVENTS, PlanEvent, PlanManager, resting_stop)
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.time_exit import TIME_EVENTS
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
from tests.planning.test_plan_manager_pending import _pending

RTH = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)      # Thursday, regular session
PRE = dt.datetime(2026, 8, 27, 8, 0, tzinfo=US_MARKET_TZ)       # pre-market (14:00 Berlin)
AFTER = dt.datetime(2026, 8, 27, 16, 30, tzinfo=US_MARKET_TZ)   # after-hours (22:30 Berlin)


@pytest.fixture(autouse=True)
def _pinned_flags(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "EXTENDED_HOURS_EXIT_CHECK", True)
    monkeypatch.setattr(config, "TRAIL_NOTIFY_MIN_R", 0.25)
    monkeypatch.setattr(config, "PYRAMIDING_ENABLED", False)


def _manager():
    return PlanManager(PlanStore(), lambda ticker: 0.0)


def _env(prices, plan=None):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore()
    store.add(plan if plan is not None else _active())
    return store, PlanManager(store, feed.get_price)


def _short():
    plan = _plan(entry_type="market", direction="bearish", trigger_price=100.0,
                 entry_price=100.0, stop_loss=105.0, tp1=90.0, tp2=None)
    record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    return plan


def test_the_band_is_a_quarter_of_initial_risk():
    assert NEAR_STOP_R == 0.25


def test_an_active_long_within_the_band_emits_stop_price_and_r_distance():
    events = _manager()._near_stop_event(_active(), 96.0, RTH)
    assert len(events) == 1
    event = events[0]
    assert (event.plan_id, event.transition) == ("p1", "near_stop")
    assert event.detail == {"stop": 95.0, "price": 96.0, "r_dist": pytest.approx(0.2)}


@pytest.mark.parametrize("price, fires", [(96.25, True), (96.3, False), (95.0, True),
                                          (94.99, False)])
def test_the_band_edges_and_the_stop_itself(price, fires):
    assert bool(_manager()._near_stop_event(_active(), price, RTH)) is fires


def test_a_short_is_measured_above_its_stop():
    manager = _manager()
    [event] = manager._near_stop_event(_short(), 104.0, RTH)
    assert event.detail == {"stop": 105.0, "price": 104.0, "r_dist": pytest.approx(0.2)}
    assert manager._near_stop_event(_short(), 105.5, RTH) == []      # beyond the stop
    assert manager._near_stop_event(_short(), 103.0, RTH) == []      # 0.4R away


def test_a_breakeven_stop_is_measured_in_initial_r():
    plan = _active(working_stop=100.0)
    [event] = _manager()._near_stop_event(plan, 101.0, RTH)
    assert event.detail["stop"] == resting_stop(plan) == 100.0
    assert event.detail["r_dist"] == pytest.approx(0.2)


@pytest.mark.parametrize("working_stop", [None, 108.0])
def test_a_partial_runner_uses_its_resting_stop(working_stop):
    plan = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 tp2=None, working_stop=working_stop)
    stop = resting_stop(plan)
    [event] = _manager()._near_stop_event(plan, stop + 0.5, RTH)
    assert event.detail["stop"] == pytest.approx(stop)
    assert event.detail["r_dist"] == pytest.approx(0.1)


@pytest.mark.parametrize("plan", [
    _pending(),
    _plan(status="CLOSED", entry_price=100.0),
    _plan(status="CANCELLED"),
])
def test_only_active_and_partial_plans_can_be_near_their_stop(plan):
    assert _manager()._near_stop_event(plan, 95.5, RTH) == []


@pytest.mark.parametrize("now", [PRE, AFTER])
def test_extended_hours_never_arm_it(now):
    assert _manager()._near_stop_event(_active(), 96.0, now) == []


def test_extended_hours_stay_unarmed_without_the_rth_gate(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    assert _manager()._near_stop_event(_active(), 96.0, PRE) == []


@pytest.mark.parametrize("price", [None, 0.0])
def test_no_price_no_event(price):
    assert _manager()._near_stop_event(_active(), price, RTH) == []


def test_zero_initial_risk_never_divides():
    plan = _plan(status="ACTIVE", entry_price=100.0, stop_loss=100.0)
    assert _manager()._near_stop_event(plan, 100.0, RTH) == []


def test_poll_emits_it_on_every_in_band_tick_and_writes_nothing():
    store, manager = _env([96.0, 96.0])
    before = store.get("p1")
    assert [e.transition for e in manager.poll(now=RTH)] == ["near_stop"]
    assert [e.transition for e in manager.poll(now=RTH)] == ["near_stop"]   # the notifier dedupes
    after = store.get("p1")
    assert (after.status, after.working_stop, after.notified_stop) == (
        before.status, before.working_stop, before.notified_stop)


def test_a_gap_beyond_the_stop_fires_closed_only():
    _store, manager = _env([94.5])
    assert [e.transition for e in manager.poll(now=RTH)] == ["closed"]


def test_poll_in_pre_market_emits_nothing():
    _store, manager = _env([96.0])
    assert manager.poll(now=PRE) == []


def test_near_stop_is_follow_only():
    assert FOLLOW_ONLY_EVENTS == frozenset({"near_stop"})
    assert not FOLLOW_ONLY_EVENTS & (STOP_EVENTS | NOTICE_EVENTS | TIME_EVENTS)


def test_the_execution_feed_never_posts_a_near_stop(monkeypatch):
    from swingbot.core.planning import plan_store
    from swingbot.core.scanning.embeds import notify_plan_events

    sent, reads = [], []

    class Chan:
        async def send(self, **kwargs):
            sent.append(kwargs)

    class Store:
        def get(self, plan_id):
            reads.append(plan_id)
            return _active()

    monkeypatch.setattr(plan_store, "PlanStore", Store)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "1", raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "2", raising=False)
    bot = types.SimpleNamespace(get_channel=lambda _id: Chan())
    event = PlanEvent("p1", "near_stop", {"stop": 95.0, "price": 96.0, "r_dist": 0.2})
    assert asyncio.run(notify_plan_events(bot, [event])) == []
    assert sent == [] and reads == []


def test_the_session_gate_is_the_regular_session(monkeypatch):
    seen = []
    monkeypatch.setattr(plan_manager, "is_regular_session", lambda now=None: seen.append(now) or True)
    assert plan_manager._arms_near_stop(PRE) is True
    assert seen == [PRE]
