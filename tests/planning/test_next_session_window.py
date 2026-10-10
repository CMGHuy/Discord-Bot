"""v144: an outlook plan rests for exactly its valid_session (RTH open to the
official close, computed in ET) and is cancelled with a catalogue reason.
Regular plans and the compression short are untouched."""
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan

ET = ZoneInfo("America/New_York")
BERLIN = ZoneInfo("Europe/Berlin")
D = dt.date(2026, 10, 12)


def _outlook(**kw):
    base = dict(plan_id="o1", source="confluence", entry_type="stop_entry", direction="bullish",
                trigger_price=102.0, stop_loss=100.5, tp1=106.0, tp2=None, expiry_bars=5,
                created_at="2026-10-09", origin="next_session", valid_session=D.isoformat())
    base.update(kw)
    return _plan(**base)


def _daily(d_high=101.40):
    days = pd.bdate_range(end=pd.Timestamp(D), periods=20)
    rows = [(100.0, 100.75, 99.25, 100.0, 1e6)] * 19 + [(101.0, d_high, 100.8, 101.2, 1e6)]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=days)


def _poll(price, when, plan=None, daily=None):
    store = PlanStore()
    store.add(plan or _outlook())
    mgr = PlanManager(store, FakePriceFeed([("AAPL", price)]).get_price,
                      daily_frame_fn=lambda t: daily, hourly_frame_fn=lambda t: None)
    events = mgr.poll(now=when)
    return store.get((plan or _outlook()).plan_id), events


def test_a_pre_open_print_through_the_trigger_never_fills():
    plan, events = _poll(103.0, dt.datetime(2026, 10, 12, 9, 0, tzinfo=ET))
    assert plan.status == PlanStatus.PENDING and events == []


def test_the_day_before_d_never_fills():
    plan, events = _poll(103.0, dt.datetime(2026, 10, 9, 15, 0, tzinfo=ET))
    assert plan.status == PlanStatus.PENDING and events == []


def test_an_rth_print_through_the_trigger_fills():
    plan, events = _poll(102.3, dt.datetime(2026, 10, 12, 10, 0, tzinfo=ET))
    assert plan.status == PlanStatus.ACTIVE and plan.entry_price == 102.3
    assert [e.transition for e in events] == ["filled"]


def test_after_the_close_it_is_cancelled_never_triggered_with_the_distance():
    plan, events = _poll(101.0, dt.datetime(2026, 10, 12, 16, 5, tzinfo=ET), daily=_daily())
    assert plan.status == PlanStatus.CANCELLED
    assert plan.status_history[-1]["reason"] == "never_triggered"
    assert plan.status_history[-1]["at"] == "2026-10-12T16:00:00-04:00"   # the real close
    message = "High 101.40 stopped 0.6% (0.4 ATR) short of the 102.00 trigger"
    assert plan.cancel_reason_message == message
    (event,) = events
    assert event.transition == "cancelled_expired"
    assert event.detail["reason_code"] == "never_triggered" and event.detail["reason_message"] == message
    assert event.detail["eligible_session"] == "2026-10-12" and event.detail["cancel_resting_order"] is True


def test_no_bar_for_d_is_no_session_data():
    plan, _ = _poll(101.0, dt.datetime(2026, 10, 12, 16, 5, tzinfo=ET), daily=None)
    assert plan.status_history[-1]["reason"] == "no_session_data"


def test_a_late_poll_the_next_morning_still_records_the_real_close():
    plan, _ = _poll(101.0, dt.datetime(2026, 10, 13, 8, 30, tzinfo=ET), daily=_daily())
    assert plan.status_history[-1]["at"] == "2026-10-12T16:00:00-04:00"


def test_a_filled_outlook_plan_is_not_cancelled_at_the_close():
    store = PlanStore()
    store.add(_outlook())
    feed = FakePriceFeed([("AAPL", 102.3), ("AAPL", 103.0)])
    mgr = PlanManager(store, feed.get_price, daily_frame_fn=lambda t: _daily(), hourly_frame_fn=lambda t: None)
    mgr.poll(now=dt.datetime(2026, 10, 12, 10, 0, tzinfo=ET))
    mgr.poll(now=dt.datetime(2026, 10, 12, 16, 5, tzinfo=ET))
    assert store.get("o1").status == PlanStatus.ACTIVE


def test_invalidated_in_session_carries_its_message():
    plan, events = _poll(100.4, dt.datetime(2026, 10, 12, 11, 0, tzinfo=ET))
    assert plan.status_history[-1]["reason"] == "invalidated"
    assert events[0].detail["reason_code"] == "invalidated"
    assert plan.cancel_reason_message == \
        "Traded 100.40 through the 100.50 stop before triggering; the setup broke"


def test_risk_cap_at_the_fill_carries_its_message():
    plan, events = _poll(103.0, dt.datetime(2026, 10, 12, 9, 31, tzinfo=ET))
    assert plan.status_history[-1]["reason"] == "risk_cap"
    assert events[0].detail["reason_message"].startswith("Gapped to 103.00 past the 102.00 trigger;")


def test_a_half_day_closes_at_1300_et():
    half = dict(valid_session="2026-11-27", created_at="2026-11-25")
    open_plan, _ = _poll(101.0, dt.datetime(2026, 11, 27, 12, 30, tzinfo=ET), plan=_outlook(**half))
    assert open_plan.status == PlanStatus.PENDING
    shut, _ = _poll(101.0, dt.datetime(2026, 11, 27, 13, 5, tzinfo=ET), plan=_outlook(plan_id="o2", **half))
    assert shut.status == PlanStatus.CANCELLED
    assert shut.status_history[-1]["at"] == "2026-11-27T13:00:00-05:00"


def test_the_dst_mismatch_week_opens_at_1430_berlin():
    week = dict(valid_session="2027-03-15", created_at="2027-03-12")
    early, _ = _poll(102.3, dt.datetime(2027, 3, 15, 14, 25, tzinfo=BERLIN), plan=_outlook(**week))
    assert early.status == PlanStatus.PENDING
    filled, _ = _poll(102.3, dt.datetime(2027, 3, 15, 14, 35, tzinfo=BERLIN), plan=_outlook(plan_id="o2", **week))
    assert filled.status == PlanStatus.ACTIVE


def _regular():
    return _plan(plan_id="r1", source="confluence", entry_type="stop_entry", direction="bullish",
                 trigger_price=102.0, stop_loss=100.5, tp1=106.0, tp2=None, created_at="2026-10-09")


@pytest.mark.parametrize("with_outlook", [False, True])
def test_a_regular_plan_steps_identically_beside_an_outlook_plan(with_outlook):
    store = PlanStore()
    store.add(_regular())
    if with_outlook:
        store.add(_outlook())
    mgr = PlanManager(store, FakePriceFeed([("AAPL", 102.3)]).get_price,
                      daily_frame_fn=lambda t: None, hourly_frame_fn=lambda t: None)
    events = mgr.poll(now=dt.datetime(2026, 10, 12, 10, 0, tzinfo=ET))
    regular = store.get("r1")
    assert [(e.transition, e.detail) for e in events if e.plan_id == "r1"] == \
        [("filled", {"entry_price": 102.3, "live_price": 102.3})]
    assert (regular.status, regular.entry_price, regular.cancel_reason_message) == (PlanStatus.ACTIVE, 102.3, None)


def test_a_regular_plan_keeps_its_bar_count_expiry():
    store = PlanStore()
    store.add(_regular())
    mgr = PlanManager(store, FakePriceFeed([("AAPL", 101.0)]).get_price, bar_count_fn=lambda t, c: 6)
    (event,) = mgr.poll(now=dt.datetime(2026, 10, 19, 10, 0, tzinfo=ET))
    assert event.transition == "cancelled_expired" and event.detail == {"bars_waited": 6}
    assert store.get("r1").status_history[-1]["reason"] == "expired"
