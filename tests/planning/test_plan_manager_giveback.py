"""v176: the runner give-back on the live tick path (PlanManager._step_partial)."""
import logging

import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus, record_transition, runner_floor
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan

FLOOR = runner_floor(100.0, 110.0)                   # 106.6667
# RKLB short, plan 47f7fd16-...-376c85: best price 49.94, working stop 59.11
# (the runner floor). Entry/TP1 are back-solved so runner_floor() == 59.11.
RKLB_ENTRY, RKLB_STOP, RKLB_TP1, RKLB_E = 63.0, 66.0, 57.165, 49.94


@pytest.fixture(autouse=True)
def _giveback_on(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "PYRAMIDING_ENABLED", False)


def _runner(direction="bullish", entry=100.0, stop=95.0, tp1=110.0,
            extreme=None, working=None, ticker="AAPL"):
    """A plan already in PARTIAL: TP1 banked, runner open at its floor."""
    p = _plan(ticker=ticker, entry_type="market", direction=direction,
              trigger_price=entry, entry_price=entry, stop_loss=stop, tp1=tp1, tp2=None)
    record_transition(p, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    record_transition(p, PlanStatus.PARTIAL, reason="tp1_partial", at="t1")
    p.legs_realized = [{"fraction": 0.5, "exit_price": tp1, "r": 2.0, "reason": "tp1"}]
    p.working_stop = runner_floor(entry, tp1) if working is None else working
    p.runner_floor_session = "2000-01-01"
    p.runner_high_close = extreme
    return p


def _rklb(**kw):
    return _runner(direction="bearish", entry=RKLB_ENTRY, stop=RKLB_STOP, tp1=RKLB_TP1,
                   extreme=RKLB_E, ticker="RKLB", **kw)


def _env(plan, atr_fn=None):
    store = PlanStore()
    store.add(plan)
    return store, PlanManager(store, FakePriceFeed().get_price, atr_fn=atr_fn)


def step(store, mgr, price):
    return mgr._step_partial(store.get("p1"), price)


def test_rklb_fixture_floor_is_the_live_working_stop():
    assert runner_floor(RKLB_ENTRY, RKLB_TP1) == pytest.approx(59.11)


def test_long_runner_tightens_to_the_giveback_level():
    store, mgr = _env(_runner())
    assert step(store, mgr, 120.0) == []
    plan = store.get("p1")
    assert plan.runner_high_close == 120.0
    assert plan.working_stop == pytest.approx(114.0)        # 120 x 0.95 > floor 106.67
    assert plan.status == PlanStatus.PARTIAL


def test_short_runner_with_an_unchanged_extreme_still_tightens():
    # RKLB at deploy: E = 49.94 never changes, price bounced to 52.30.
    store, mgr = _env(_rklb())
    assert step(store, mgr, 52.30) == []
    plan = store.get("p1")
    assert plan.runner_high_close == RKLB_E
    assert plan.working_stop == pytest.approx(52.437)       # 49.94 x 1.05, was 59.11
    assert plan.status == PlanStatus.PARTIAL


def test_first_tick_already_past_the_level_moves_and_closes_on_one_tick():
    store, mgr = _env(_rklb())
    events = step(store, mgr, 52.60)                         # >= 52.437 for a short
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_trail"   # no new reason string
    assert events[0].detail["exit_price"] == 52.60            # live fill = the tick
    leg = events[0].detail["leg"]
    assert leg["stop_source"] == "giveback"
    assert leg["giveback_pct"] == 5.0
    assert leg["giveback_extreme"] == RKLB_E
    assert leg["giveback_stop"] == pytest.approx(52.437)
    assert leg["r"] == pytest.approx((RKLB_ENTRY - 52.60) / (RKLB_STOP - RKLB_ENTRY))
    plan = store.get("p1")
    assert plan.status == PlanStatus.CLOSED
    assert plan.working_stop == pytest.approx(52.437)


def test_never_loosens_when_the_trail_is_already_tighter():
    store, mgr = _env(_runner(extreme=120.0, working=118.0))
    step(store, mgr, 119.0)
    assert store.get("p1").working_stop == 118.0             # give-back 114 is looser


def test_never_loosens_when_the_floor_is_already_tighter():
    store, mgr = _env(_runner())
    step(store, mgr, 107.5)                                   # give-back 102.1 < floor
    assert store.get("p1").working_stop == pytest.approx(FLOOR)


def test_no_extreme_means_no_giveback_term():
    store, mgr = _env(_runner())
    plan = store.get("p1")
    mgr._apply_giveback(plan, 120.0)                          # E is None: nothing to do
    assert store.get("p1").working_stop == pytest.approx(FLOOR)


def test_flag_off_never_loosens_a_stop_already_tightened(monkeypatch):
    store, mgr = _env(_runner(extreme=120.0, working=114.0))
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    step(store, mgr, 116.0)
    assert store.get("p1").working_stop == 114.0


def test_flag_off_stops_new_tightening(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    store, mgr = _env(_runner())
    step(store, mgr, 120.0)
    assert store.get("p1").working_stop == pytest.approx(FLOOR)


@pytest.mark.parametrize("enabled", [False, True])
def test_trail_path_is_unchanged_when_the_chandelier_is_tighter(monkeypatch, enabled):
    # ATR 2.0 x trail_atr_mult 2.5 -> trail = extreme - 5.0; give-back is
    # extreme x 0.95, looser at these prices, so both arms match pre-v176.
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", enabled)
    store, mgr = _env(_runner(), atr_fn=lambda t: 2.0)
    assert step(store, mgr, 120.0) == []
    assert store.get("p1").working_stop == 115.0
    assert step(store, mgr, 118.0) == []
    assert store.get("p1").working_stop == 115.0
    events = step(store, mgr, 114.9)
    assert events[0].detail["reason"] == "tp1_runner_trail"
    assert events[0].detail["leg"]["stop_source"] == "trail"
    assert "giveback_stop" not in events[0].detail["leg"]


def test_isolated_spike_print_sets_the_extreme_for_good():
    # Accepted behaviour (spec § Risks): an extended-hours spike to 130 sets
    # E = 130 permanently; the give-back then sits at 123.5.
    store, mgr = _env(_runner())
    step(store, mgr, 130.0)
    assert store.get("p1").working_stop == pytest.approx(123.5)
    events = step(store, mgr, 122.0)
    assert events[0].detail["reason"] == "tp1_runner_trail"
    assert events[0].detail["leg"]["stop_source"] == "giveback"
    assert events[0].detail["leg"]["giveback_extreme"] == 130.0


def test_manager_without_atr_fn_still_tracks_the_extreme_and_applies_it():
    store, mgr = _env(_runner(), atr_fn=None)
    step(store, mgr, 120.0)
    step(store, mgr, 125.0)
    plan = store.get("p1")
    assert plan.runner_high_close == 125.0
    assert plan.working_stop == pytest.approx(118.75)


def test_floor_close_carries_stop_source_floor():
    store, mgr = _env(_runner())
    events = step(store, mgr, 106.0)                          # below the floor 106.67
    assert events[0].detail["reason"] == "tp1_runner_be"
    leg = events[0].detail["leg"]
    assert leg["stop_source"] == "floor"
    assert "giveback_pct" not in leg


def test_giveback_line_is_logged_only_when_the_stop_moves(caplog):
    store, mgr = _env(_runner())
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.plan_manager"):
        step(store, mgr, 120.0)
        step(store, mgr, 119.0)                               # same E, same level
    lines = [r.getMessage() for r in caplog.records if "giveback stop" in r.getMessage()]
    assert len(lines) == 1
    assert "AAPL" in lines[0]
