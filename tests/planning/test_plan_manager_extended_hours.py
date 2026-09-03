"""v70: extended-hours terminal exits. Injected clock, no network, no
sleeps -- the same style as the rest of tests/planning/test_plan_manager_*."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active

# 2026-08-27 is a Thursday; 08-29/08-30 are Saturday/Sunday.
PREMARKET = dt.datetime(2026, 8, 27, 8, 30, tzinfo=US_MARKET_TZ)
RTH = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)
AFTER_HOURS = dt.datetime(2026, 8, 27, 19, 30, tzinfo=US_MARKET_TZ)
QUIET = dt.datetime(2026, 8, 27, 2, 0, tzinfo=US_MARKET_TZ)
SATURDAY = dt.datetime(2026, 8, 29, 12, 0, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def _v70_defaults(monkeypatch):
    """Pin every flag this file depends on, so a dev machine's .env can
    never decide the outcome of a test."""
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "EXTENDED_HOURS_EXIT_CHECK", True)
    monkeypatch.setattr(config, "EXTENDED_HOURS_DEBOUNCE_TICKS", 2)
    monkeypatch.setattr(config, "QUIET_HOURS_START_ET", 23)
    monkeypatch.setattr(config, "QUIET_HOURS_END_ET", 8)


def _env(tmp_path, prices=(), plan=None):
    """_active() is entry 100, stop 95, tp1 110, tp1_fraction 0.5, so risk
    is 5.00 and runner_floor(100, 110) is 106.67."""
    feed = FakePriceFeed()
    feed.set_series("AAPL", list(prices))
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(plan if plan is not None else _active())
    return store, PlanManager(store, feed.get_price)


def _partial_env(tmp_path, tp2=None, floor_session="2026-08-26"):
    """An ACTIVE plan walked through TP1, with the runner floor stamped to
    an EARLIER session so v64's same-session guard is satisfied."""
    feed = FakePriceFeed()
    feed.set_series("AAPL", [110.5])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active(tp2=tp2))
    mgr = PlanManager(store, feed.get_price)
    assert [e.transition for e in mgr.poll(now=RTH)] == ["tp1_partial"]
    plan = store.get("p1")
    plan.runner_floor_session = floor_session
    store.update(plan)
    return store, mgr


def test_one_breach_tick_never_closes(tmp_path):
    store, mgr = _env(tmp_path)
    plan = store.get("p1")
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_a_reverting_tick_clears_the_streak_entirely(tmp_path):
    store, mgr = _env(tmp_path)
    plan = store.get("p1")
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []
    assert mgr._eh_breach_streak["p1"] == ("active_stop", 1)
    assert mgr._step_extended(plan, 99.0, AFTER_HOURS) == []   # back above the stop
    assert "p1" not in mgr._eh_breach_streak                   # popped, not decremented
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []   # counting starts over
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_two_confirming_ticks_close_at_the_second_tick_price(tmp_path):
    store, mgr = _env(tmp_path)
    plan = store.get("p1")
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []
    events = mgr._step_extended(plan, 93.5, AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "loss"
    assert events[0].detail["exit_price"] == 93.5    # the confirming print, never 95.0
    assert store.get("p1").status == PlanStatus.CLOSED
    assert "p1" not in mgr._eh_breach_streak


def test_a_break_even_stop_closes_as_a_scratch_from_the_next_session(tmp_path):
    store, mgr = _env(tmp_path, plan=_active(working_stop=100.0,
                                             be_armed_session="2026-08-26"))
    plan = store.get("p1")
    assert mgr._step_extended(plan, 99.5, AFTER_HOURS) == []
    events = mgr._step_extended(plan, 99.4, AFTER_HOURS)
    assert events[0].detail["reason"] == "scratch"
    assert events[0].detail["exit_price"] == 99.4


def test_a_stop_armed_this_session_does_not_govern_extended_hours(tmp_path):
    """v64's rule, unchanged: a break-even stop governs from the session
    AFTER it armed, so the original 95.00 stop is still the live one."""
    store, mgr = _env(tmp_path, plan=_active(working_stop=100.0,
                                             be_armed_session="2026-08-27"))
    plan = store.get("p1")
    for _ in range(4):
        assert mgr._step_extended(plan, 99.4, AFTER_HOURS) == []
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_tp1_with_a_tp2_still_to_run_is_inert(tmp_path):
    store, mgr = _env(tmp_path, plan=_active(tp2=120.0))
    plan = store.get("p1")
    for _ in range(5):
        assert mgr._step_extended(plan, 111.0, AFTER_HOURS) == []
    p = store.get("p1")
    assert p.status == PlanStatus.ACTIVE
    assert p.legs_realized == []
    assert p.working_stop is None


def test_tp1_with_no_tp2_is_terminal_and_closes_as_a_win(tmp_path):
    store, mgr = _env(tmp_path, plan=_active(tp2=None))
    plan = store.get("p1")
    assert mgr._step_extended(plan, 110.5, AFTER_HOURS) == []
    events = mgr._step_extended(plan, 111.0, AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "win"
    assert events[0].detail["exit_price"] == 111.0
    assert store.get("p1").status == PlanStatus.CLOSED


def test_the_break_even_trigger_never_arms_outside_regular_hours(tmp_path):
    """105.00 is the BE trigger for this plan (halfway to TP1). In RTH it
    arms a working stop; extended hours must leave the plan untouched."""
    store, mgr = _env(tmp_path)
    plan = store.get("p1")
    for _ in range(4):
        assert mgr._step_extended(plan, 105.0, AFTER_HOURS) == []
    assert store.get("p1").working_stop is None


def test_a_pending_plan_never_moves_on_an_extended_hours_tick(tmp_path):
    store, mgr = _env(tmp_path, plan=_plan())      # PENDING, trigger 100
    plan = store.get("p1")
    for price in (101.0, 101.0, 101.0, 90.0, 90.0):
        assert mgr._step_extended(plan, price, AFTER_HOURS) == []
    assert store.get("p1").status == PlanStatus.PENDING


def test_a_runner_stop_closes_at_the_floor_reason(tmp_path):
    store, mgr = _partial_env(tmp_path)
    plan = store.get("p1")
    assert mgr._step_extended(plan, 106.0, AFTER_HOURS) == []    # floor is 106.67
    events = mgr._step_extended(plan, 105.5, AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == 105.5
    p = store.get("p1")
    assert p.status == PlanStatus.CLOSED
    assert len(p.legs_realized) == 2


def test_a_runner_closes_at_tp2(tmp_path):
    store, mgr = _partial_env(tmp_path, tp2=118.0)
    plan = store.get("p1")
    assert mgr._step_extended(plan, 118.5, AFTER_HOURS) == []
    events = mgr._step_extended(plan, 119.0, AFTER_HOURS)
    assert events[0].detail["reason"] == "tp1_runner_tp2"
    assert events[0].detail["exit_price"] == 119.0


def test_the_runner_floor_is_inert_in_its_own_session(tmp_path):
    store, mgr = _partial_env(tmp_path, floor_session="2026-08-27")
    plan = store.get("p1")
    for _ in range(4):
        assert mgr._step_extended(plan, 100.0, AFTER_HOURS) == []
    assert store.get("p1").status == PlanStatus.PARTIAL


def test_the_trailing_ratchet_never_runs_outside_regular_hours(tmp_path):
    """_step_extended takes no atr_fn path at all: a new extreme must not
    move working_stop, whatever the ATR would have said."""
    store, mgr = _partial_env(tmp_path)
    mgr.atr_fn = lambda ticker: 2.0
    plan = store.get("p1")
    before = store.get("p1").working_stop
    assert mgr._step_extended(plan, 115.0, AFTER_HOURS) == []
    assert store.get("p1").working_stop == before
    assert store.get("p1").runner_high_close is None


def test_a_different_breach_cannot_finish_another_ones_streak(tmp_path):
    """The generalisation of the spec's pop-don't-decrement rule: a stop
    tick and a target tick are different breaches, so the second starts its
    own count rather than completing the first's."""
    store, mgr = _env(tmp_path, plan=_active(tp2=None))
    plan = store.get("p1")
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []     # stop, streak 1
    assert mgr._step_extended(plan, 111.0, AFTER_HOURS) == []    # tp1, streak 1 again
    assert mgr._eh_breach_streak["p1"] == ("tp1", 1)
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_the_debounce_count_is_read_from_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXTENDED_HOURS_DEBOUNCE_TICKS", 1)
    store, mgr = _env(tmp_path)
    plan = store.get("p1")
    events = mgr._step_extended(plan, 94.0, AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]


def test_cross_status_collision_does_not_occur(tmp_path):
    """A leftover ACTIVE-stop streak must NOT be completed by an unrelated
    PARTIAL-stop breach on the same plan_id. Regression test for critical
    bug: status-aware kind strings prevent the streak from carrying over
    across plan transitions.

    Sequence: (1) Evening, ACTIVE: 1 tick of active_stop below threshold
    (2) Next day RTH: plan transitions ACTIVE -> PARTIAL via TP1 hit
    (3) Evening, PARTIAL: 1 tick of partial_stop at runner floor

    Without the fix, step (3) would see the leftover streak from (1),
    bump it to 2, and close immediately. With the fix, the active_stop
    streak from (1) is invisible to the partial_stop breach in (3)."""
    feed = FakePriceFeed()
    feed.set_series("AAPL", [110.5, 105.5])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())
    mgr = PlanManager(store, feed.get_price)

    # Step 1: Evening, ACTIVE plan: 1 tick of stop breach, not yet confirming
    plan = store.get("p1")
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []
    assert mgr._eh_breach_streak["p1"] == ("active_stop", 1)
    assert store.get("p1").status == PlanStatus.ACTIVE

    # Step 2: Next day, regular hours: transition ACTIVE -> PARTIAL via TP1 hit
    # The manager instance is kept; _eh_breach_streak is NOT reset.
    events = mgr.poll(now=RTH)
    assert [e.transition for e in events] == ["tp1_partial"]
    plan = store.get("p1")
    assert plan.status == PlanStatus.PARTIAL
    # Streak from ACTIVE-stop is still in memory (no revert popped it, no confirm closed it)
    assert mgr._eh_breach_streak["p1"] == ("active_stop", 1)

    # Step 3: Evening, PARTIAL plan: 1 tick of runner-floor breach (partial_stop)
    # This MUST NOT inherit or complete the active_stop streak from step 1.
    # Setting runner_floor_session to an earlier date to satisfy the guard.
    plan.runner_floor_session = "2026-08-26"
    store.update(plan)
    assert mgr._step_extended(plan, 105.5, AFTER_HOURS) == []
    # The partial_stop breach started a NEW streak (streak=1), not continuing the active_stop one
    assert mgr._eh_breach_streak["p1"] == ("partial_stop", 1)
    assert store.get("p1").status == PlanStatus.PARTIAL

    # One more confirming tick: should close because partial_stop now has 2 ticks
    events = mgr._step_extended(plan, 105.0, AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
    assert store.get("p1").status == PlanStatus.CLOSED
