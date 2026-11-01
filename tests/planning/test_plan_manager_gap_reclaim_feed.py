"""V192-11: the waiting market plan's open-time events reach the execution feed's
re-send queue, the INFO log and the trade-log placeholder. DB-backed."""
import logging

import pytest

from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_engine import PlanStatus
from tests.planning.test_plan_manager_market_open import (OPEN, PREMARKET, _Log, _bull, _env,  # noqa: F401
                                                         _et, _flags, _tr)

NEW = {"cancelled_open_through_stop", "cancelled_gap_no_reclaim", "gap_reclaim_order"}
NEW_CANCELS = {"cancelled_open_through_stop", "cancelled_gap_no_reclaim"}


def test_the_new_events_are_feed_notices_and_none_is_follow_only():
    assert NEW <= pm.NOTICE_EVENTS
    assert not NEW & pm.FOLLOW_ONLY_EVENTS


def test_the_placeholder_discard_set_is_the_pending_cancel_set():
    # v187 D3: one set drives the discard and the notices; v192's two cancels join it.
    assert pm.PLACEHOLDER_DISCARD_EVENTS is pm.PENDING_CANCEL_EVENTS
    assert NEW_CANCELS <= pm.PLACEHOLDER_DISCARD_EVENTS
    assert "gap_reclaim_order" not in pm.PLACEHOLDER_DISCARD_EVENTS


def test_the_reclaim_order_is_queued_resent_and_acknowledged():
    store, mgr = _env(_bull(reclaim_level=99.5, reclaim_atr=2.0), [99.0, 99.2])
    first = mgr.poll(OPEN)
    assert _tr(first) == ["gap_reclaim_order"]
    notice = store.get("p1").pending_notice
    assert notice["transition"] == "gap_reclaim_order" and notice["detail"] == first[0].detail
    again = mgr.poll(_et(14, 9, 32))                   # not acked yet: re-sent
    assert [e.detail for e in again if e.transition == "gap_reclaim_order"] == [first[0].detail]
    pm.ack_notified([pm.Delivery("p1", "notice", "gap_reclaim_order")])
    assert store.get("p1").pending_notice is None


def test_the_reclaim_fill_replaces_the_queued_order():
    store, mgr = _env(_bull(reclaim_level=99.5, reclaim_atr=2.0), [99.0, 100.01])
    mgr.poll(OPEN)
    events = mgr.poll(_et(14, 10))
    assert "filled" in _tr(events)
    assert store.get("p1").pending_notice["transition"] == "filled"


def test_the_close_cancel_replaces_the_queued_order_and_drops_the_placeholder():
    log = _Log()
    store, mgr = _env(_bull(reclaim_level=99.5, reclaim_atr=2.0), [99.0, 99.2], trade_log=log)
    mgr.poll(OPEN)
    events = mgr.poll(_et(14, 16, 5))
    assert "cancelled_gap_no_reclaim" in _tr(events)
    assert store.get("p1").pending_notice["transition"] == "cancelled_gap_no_reclaim"
    assert log.calls == [("discard", "p1")]


def test_the_reclaim_order_keeps_the_placeholder():
    log = _Log()
    _store, mgr = _env(_bull(reclaim_level=99.5, reclaim_atr=2.0), [99.0], trade_log=log)
    assert _tr(mgr.poll(OPEN)) == ["gap_reclaim_order"]
    assert log.calls == []


@pytest.mark.parametrize("now, prices", [(OPEN, [98.0]), (PREMARKET, [98.0, 98.0])])
def test_a_through_stop_cancel_is_queued_and_drops_the_placeholder(now, prices):
    log = _Log()
    store, mgr = _env(_bull(), prices, trade_log=log)
    for _ in prices:
        mgr.poll(now)
    plan = store.get("p1")
    assert plan.status == PlanStatus.CANCELLED
    assert plan.pending_notice["transition"] == "cancelled_open_through_stop"
    assert log.calls == [("discard", "p1")]


def test_each_new_event_writes_its_info_line(caplog):
    caplog.set_level(logging.INFO, logger=pm.log.name)
    _store, mgr = _env(_bull(reclaim_level=99.5, reclaim_atr=2.0), [99.0, 99.2])
    mgr.poll(OPEN)
    mgr.poll(_et(14, 16, 5))
    text = caplog.text
    assert "Plan reclaim order at entry: AAPL id=p1 bullish price=100.00" in text
    assert "Plan no reclaim: AAPL id=p1 bullish price=100.00" in text
    caplog.clear()
    _store, mgr = _env(_bull(plan_id="p2"), [98.0])
    mgr.poll(OPEN)
    assert "Plan opened through stop: AAPL id=p2 bullish price=98.00" in caplog.text
