"""What poll() does at each hour of the clock. Injected clock, no network,
no sleeps -- the same style as the rest of tests/planning/test_plan_manager_*.

Two windows govern the live manager, and they are NOT the same window:

- **The poll window** (`is_quiet_hours`, Berlin-anchored): whether poll()
  runs the state machine at all. Since 2026-09-14 that is the only gate --
  the FULL machine runs single-tick across all of it, replacing v70's
  narrower debounced extended-hours mode (deleted, along with this file's
  former half that tested it directly).
- **The tape window** (`is_tape_open`, 04:00-20:00 ET): whether a quote
  taken right now reflects something that actually just traded. Only this
  one may record `_last_seen`, which lets a stop fill AT the stop.

The poll window opens at 08:00 Berlin = 02:00 ET, two hours before the
tape does, which is exactly where conflating the two cost real money --
see test_a_tick_before_the_tape_opens_does_not_make_the_rth_fill_continuous.
"""
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

# 2026-08-27 is a Thursday; 08-29/08-30 are Saturday/Sunday. The quiet window
# is Berlin-anchored (23:00-08:00 Europe/Berlin, +6h from ET in August), so
# AFTER_HOURS and QUIET are picked to land on the intended side of that
# window's Berlin-time boundary, not just outside RTH in ET.
PREMARKET = dt.datetime(2026, 8, 27, 8, 30, tzinfo=US_MARKET_TZ)     # 14:30 Berlin: polled, tape open
RTH = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)
AFTER_HOURS = dt.datetime(2026, 8, 27, 16, 30, tzinfo=US_MARKET_TZ)  # 22:30 Berlin: polled, tape open
#: Polled (08:30 Berlin, just past the quiet window) but BEFORE the tape
#: opens at 04:00 ET -- the two-hour gap the poll/tape distinction exists for.
PRE_TAPE = dt.datetime(2026, 8, 27, 2, 30, tzinfo=US_MARKET_TZ)
QUIET = dt.datetime(2026, 8, 27, 0, 30, tzinfo=US_MARKET_TZ)         # 06:30 Berlin: quiet
SATURDAY = dt.datetime(2026, 8, 29, 12, 0, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def _flag_defaults(monkeypatch):
    """Pin every flag this file depends on, so a dev machine's .env can
    never decide the outcome of a test."""
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "QUIET_HOURS_START_BERLIN", 23)
    monkeypatch.setattr(config, "QUIET_HOURS_END_BERLIN", 8)


def _env(tmp_path, prices=(), plan=None):
    """_active() is entry 100, stop 95, tp1 110, tp1_fraction 0.5, so risk
    is 5.00 and runner_floor(100, 110) is 106.67."""
    feed = FakePriceFeed()
    feed.set_series("AAPL", list(prices))
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(plan if plan is not None else _active())
    return store, PlanManager(store, feed.get_price)


def _partial_env(tmp_path, tp2=None, floor_session="2026-08-26"):
    """An ACTIVE plan walked through TP1, with the runner floor stamped.
    Defaults to an earlier session; v64's same-session guard this used to
    need satisfying is gone (removed 2026-09-10), but callers may still
    pass floor_session="today" to test same-session behaviour explicitly."""
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

def test_after_hours_polls_close_the_plan_immediately(tmp_path):
    """Widened 2026-09-14: the full machine runs single-tick, no debounce,
    same as RTH -- a stop hit closes on the FIRST after-hours poll now,
    not the second."""
    store, mgr = _env(tmp_path, [94.0])
    events = mgr.poll(now=AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["exit_price"] == 94.0
    assert store.get("p1").status == PlanStatus.CLOSED


def test_premarket_polls_close_the_plan_too(tmp_path):
    store, mgr = _env(tmp_path, [94.0])
    assert [e.transition for e in mgr.poll(now=PREMARKET)] == ["closed"]


def test_quiet_hours_are_fully_dark(tmp_path):
    store, mgr = _env(tmp_path, [94.0, 93.5, 93.0, 92.5])
    for _ in range(4):
        assert mgr.poll(now=QUIET) == []
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_the_whole_weekend_is_fully_dark(tmp_path):
    store, mgr = _env(tmp_path, [94.0, 93.5])
    assert mgr.poll(now=SATURDAY) == []
    assert mgr.poll(now=SATURDAY) == []
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_rth_only_off_still_runs_the_full_machine_round_the_clock(tmp_path, monkeypatch):
    """The pre-v64 escape hatch is untouched: with INTRADAY_RTH_ONLY off an
    overnight tick takes the FULL _step branch -- one tick, no debounce --
    and the quiet window never applies."""
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    store, mgr = _env(tmp_path, [94.0])
    assert [e.transition for e in mgr.poll(now=QUIET)] == ["closed"]


def test_regular_hours_still_arm_break_even(tmp_path):
    store, mgr = _env(tmp_path, [105.0])
    assert [e.transition for e in mgr.poll(now=RTH)] == ["be_moved"]
    assert store.get("p1").working_stop == 100.0


def test_after_hours_now_arms_break_even_too(tmp_path):
    """Headline of the 2026-09-14 widening: break-even arming was one of
    the capabilities v70 explicitly kept regular-hours-only (its own
    spec's Non-goals). It now fires after-hours too, single tick, exactly
    like RTH."""
    store, mgr = _env(tmp_path, [105.0])
    assert [e.transition for e in mgr.poll(now=AFTER_HOURS)] == ["be_moved"]
    assert store.get("p1").working_stop == 100.0


def test_after_hours_now_banks_tp1_with_a_tp2_still_to_run(tmp_path):
    """Same headline: TP1 partial-banking while a tp2 remains was the
    other capability v70 kept regular-hours-only. Now fires after-hours,
    single tick."""
    store, mgr = _env(tmp_path, [111.0], plan=_active(tp2=120.0))
    events = mgr.poll(now=AFTER_HOURS)
    assert [e.transition for e in events] == ["tp1_partial"]
    plan = store.get("p1")
    assert plan.status == PlanStatus.PARTIAL
    assert plan.working_stop is not None


def test_a_premarket_print_keeps_the_rth_fill_continuous(tmp_path):
    """Premarket (08:30 ET) is inside the TAPE window, so a print there is
    a real one: it does tell the 09:30 poll it watched the tape cross, and
    v64's poll_stop_fill fills AT the stop rather than at the gap price."""
    store, mgr = _env(tmp_path, [99.0, 94.0])
    assert mgr.poll(now=PREMARKET) == []          # above the stop: no candidate
    assert "p1" in mgr._last_seen
    events = mgr.poll(now=RTH)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["exit_price"] == 95.0    # the stop price, watched continuously


def test_a_tick_before_the_tape_opens_does_not_make_the_rth_fill_continuous(tmp_path):
    """The regression this file's poll-vs-tape distinction exists for
    (audit, 2026-09-14). 02:30 ET is INSIDE the poll window (08:30 Berlin,
    just past quiet hours) but two hours BEFORE the tape opens at 04:00
    ET. get_current_price uses prepost=True and returns yesterday's last
    after-hours print at that hour, indistinguishable from a live one.

    Recording that as `_last_seen` made _continuous() claim all day that
    we had watched the tape at 99.00, so a gap-down through the stop at
    the open filled AT the stop (95.00) instead of at the gap (88.00) --
    a better exit than anything that ever traded, written into the trade
    log as realised P&L. The fill must be the gap price."""
    store, mgr = _env(tmp_path, [99.0, 88.0])
    assert mgr.poll(now=PRE_TAPE) == []           # above the stop: no candidate
    assert "p1" not in mgr._last_seen             # and NOT recorded as watched
    events = mgr.poll(now=RTH)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["exit_price"] == 88.0    # the gap price, not the stop


def test_the_machine_still_steps_before_the_tape_opens(tmp_path):
    """The tape gate covers _last_seen ONLY -- it must not quietly
    reintroduce a second dark window. A stop already breached at 02:30 ET
    still closes on that tick, at the observed price."""
    store, mgr = _env(tmp_path, [94.0])
    events = mgr.poll(now=PRE_TAPE)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["exit_price"] == 94.0


def test_a_price_failure_on_one_plan_does_not_stop_the_others(tmp_path):
    """poll()'s existing per-plan isolation still holds."""
    feed = FakePriceFeed()
    feed.set_series("MSFT", [94.0])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())                                  # AAPL: no ticks queued
    store.add(_active(plan_id="p2", ticker="MSFT"))
    mgr = PlanManager(store, feed.get_price)
    events = mgr.poll(now=AFTER_HOURS)
    assert [(e.plan_id, e.transition) for e in events] == [("p2", "closed")]


class _RecordingLog:
    """Minimal TradeLog stand-in: PlanManager._on_event only ever calls
    reload() and close_plan_trade() on a terminal close."""

    def __init__(self):
        self.closed = []

    def reload(self):
        pass

    def close_plan_trade(self, plan_id, leg, status):
        self.closed.append((plan_id, leg, status))


def test_a_terminal_target_close_reaches_the_trade_log_as_a_win(tmp_path):
    """No special extended-hours shortcut any more (2026-09-14): a tp1 hit
    banks a partial exactly like RTH does even with no tp2 -- the OLD
    _step_extended path used to skip straight to a one-tick "win" close
    when tp2 was None, which the full machine has no equivalent of. The
    runner then closes on its own floor like any other runner, and still
    reaches the trade log as a win (close_plan_trade's reason ->
    status mapping treats every "tp1_..." reason as a win)."""
    feed = FakePriceFeed()
    feed.set_series("AAPL", [111.0, 106.0])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active(tp2=None))
    trade_log = _RecordingLog()
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log)

    assert [e.transition for e in mgr.poll(now=AFTER_HOURS)] == ["tp1_partial"]
    events = mgr.poll(now=AFTER_HOURS)              # 106.0 <= runner_floor(100, 110) == 106.67
    assert [e.transition for e in events] == ["closed"]

    plan_id, leg, status = trade_log.closed[0]
    assert (plan_id, status) == ("p1", "win")


def test_a_terminal_stop_close_still_reaches_the_trade_log_as_a_loss(tmp_path):
    feed = FakePriceFeed()
    feed.set_series("AAPL", [94.0])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())
    trade_log = _RecordingLog()
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log)

    assert [e.transition for e in mgr.poll(now=AFTER_HOURS)] == ["closed"]
    assert trade_log.closed[0][2] == "loss"
