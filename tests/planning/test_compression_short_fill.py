"""v119 Task 6: next-session fill, expiry and gap-risk parity, replay vs live.

The compression short rests a sell-stop one tick under the release low. Only
session t+1 may fill it. Replay (simulate_exit) and live (PlanManager) must
agree on the entry price, the status and the cancel reason for: a clean touch,
a bearish gap fill at the open, a gap whose planned loss breaches the cap, and
a session that never touches the trigger. The signal day -> next session hop is
counted in SESSIONS (a holiday between them is not an expiry).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.stop_scope import plan_stop_ceiling
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan

ET = ZoneInfo("America/New_York")
TRIGGER, STOP = 100.0, 101.0
SIGNAL_DAY = "2026-11-25"                   # Wed; Thu 11-26 is Thanksgiving
SESSIONS = ["2026-11-25", "2026-11-27", "2026-11-30"]
ELIGIBLE = (2026, 11, 27)                   # the only session that may fill


def _short(**kw):
    base = dict(strategy=COMPRESSION_SHORT, horizon_key="2w", direction="bearish",
                entry_type="stop_entry", trigger_price=TRIGGER, stop_loss=STOP,
                tp1=95.0, tp1_fraction=1.0, tp2=None, expiry_bars=1,
                created_at=SIGNAL_DAY)
    base.update(kw)
    return _plan(**base)


def _frame(next_bar, third_bar=(99.0, 99.5, 98.5, 99.0)):
    rows = [(100.5, 101.0, 100.0, 100.5, 1e6),    # signal bar
            (*next_bar, 1e6), (*third_bar, 1e6)]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"],
                        index=pd.DatetimeIndex(SESSIONS))


def _live(price, *, hour=10, minute=0, day=ELIGIBLE, plan=None):
    feed = FakePriceFeed([("AAPL", price)])
    store = PlanStore()
    store.add(plan or _short())
    mgr = PlanManager(store, feed.get_price)
    events = mgr.poll(now=datetime(*day, hour, minute, tzinfo=ET))
    return store.get("p1"), events


def test_no_same_bar_fill_signal_bar_through_trigger_is_ignored():
    # The signal bar itself trades through the trigger; it must not fill.
    df = _frame((100.5, 101.0, 100.2, 100.8))      # t+1 never touches 100
    df.iloc[0, df.columns.get_loc("Low")] = 99.0
    res = simulate_exit(df, 0, _short(), scale_out=True)
    assert res.outcome == "not_triggered" and res.entry_index is None


def test_trigger_touch_in_next_session_fills_at_trigger():
    df = _frame((100.4, 100.6, 99.5, 99.8))
    res = simulate_exit(df, 0, _short(), scale_out=True)
    plan, events = _live(TRIGGER)
    assert res.entry_index == 1
    assert res.entry_price == plan.entry_price == TRIGGER
    assert plan.status == PlanStatus.ACTIVE
    assert [e.transition for e in events] == ["filled"]


def test_bearish_gap_below_trigger_fills_at_the_open_in_both_paths():
    df = _frame((99.5, 99.9, 99.0, 99.2))
    res = simulate_exit(df, 0, _short(), scale_out=True)
    plan, events = _live(99.5)
    assert res.entry_price == plan.entry_price == 99.5
    assert plan.status == PlanStatus.ACTIVE


def test_gap_breaching_the_cap_is_cancelled_risk_cap_in_both_paths():
    ceiling = plan_stop_ceiling(_short())
    gap_open = STOP / (1 + ceiling / 100.0) - 1.0     # planned loss > ceiling
    df = _frame((gap_open, gap_open + 0.2, gap_open - 0.5, gap_open))
    res = simulate_exit(df, 0, _short(), scale_out=True)
    plan, events = _live(gap_open)
    assert res.outcome == "not_triggered"             # excluded, never win/loss
    assert res.cancel_reason == "risk_cap" and res.entry_price is None
    assert plan.status == PlanStatus.CANCELLED
    assert [e.transition for e in events] == ["cancelled_risk_cap"]


def test_fill_bar_that_also_hits_stop_is_a_loss_stop_first():
    # Fills at 100 then trades up to the 101 stop; the low also reaches the
    # 95 target. Stop-first ordering: a full loss, not a win.
    df = _frame((100.4, 101.2, 94.0, 96.0))
    res = simulate_exit(df, 0, _short(), scale_out=True)
    assert res.outcome == "loss" and res.entry_index == 1 and res.r_total == -1.0


def test_unfilled_next_session_expires_in_both_paths_with_cancel_instruction():
    df = _frame((100.5, 100.9, 100.2, 100.4))
    res = simulate_exit(df, 0, _short(), scale_out=True)
    plan, events = _live(100.4, hour=16, minute=5)    # just after the close
    assert res.outcome == "not_triggered" and res.cancel_reason == "expired"
    assert plan.status == PlanStatus.CANCELLED
    assert [e.transition for e in events] == ["cancelled_expired"]
    assert events[0].detail["cancel_resting_order"] is True
    assert events[0].detail["eligible_session"] == "2026-11-27"


def test_live_does_not_expire_or_fill_on_the_holiday_between_signal_and_next_session():
    plan, events = _live(99.0, day=(2026, 11, 26))    # Thanksgiving, no session
    assert events == [] and plan.status == PlanStatus.PENDING
    plan, events = _live(100.4, hour=15, minute=59)   # eligible session, still open
    assert events == [] and plan.status == PlanStatus.PENDING


def test_live_premarket_cross_before_the_eligible_open_does_not_fill():
    plan, events = _live(99.0, hour=8, minute=0)
    assert events == [] and plan.status == PlanStatus.PENDING


def test_live_late_poll_after_the_eligible_session_expires_instead_of_filling():
    plan, events = _live(99.0, day=(2026, 11, 30))
    assert [e.transition for e in events] == ["cancelled_expired"]
    assert plan.status == PlanStatus.CANCELLED


def test_non_compression_stop_entry_gap_behaviour_is_unchanged():
    # A Fibonacci bearish stop_entry gapping far past the cap still fills in
    # replay (no risk-cap check there) and still expires on its own bar count.
    plan = _plan(direction="bearish", entry_type="stop_entry", trigger_price=100.0,
                 stop_loss=110.0, tp1=90.0, tp1_fraction=1.0, tp2=None, expiry_bars=1)
    df = _frame((95.0, 95.5, 94.0, 94.5))
    res = simulate_exit(df, 0, plan, scale_out=True)
    assert res.entry_price == 95.0 and res.cancel_reason is None


def test_exit_result_cancel_reason_defaults_to_none():
    df = _frame((100.5, 100.9, 100.2, 100.4))
    plan = _plan(direction="bearish", entry_type="stop_entry", trigger_price=100.0,
                 stop_loss=110.0, tp1=90.0, tp1_fraction=1.0, tp2=None, expiry_bars=1)
    assert simulate_exit(df, 0, plan, scale_out=True).cancel_reason is None
