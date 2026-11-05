"""V192-9: a market plan resting for its reclaim -- fill at E one tick through it,
cancel at the session's close, survive a restart and a knob flip. DB-backed."""
import pytest

from swingbot import config
from swingbot.core.planning import market_open as mo
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_market_open import (OPEN, _Log, _bear, _bull, _env,  # noqa: F401
                                                         _et, _flags, _tr)


def _resting(make=_bull, **kw):
    """A plan whose deciding open sat at or beyond X: it now rests for the session."""
    level, open_price = (99.5, 99.0) if make is _bull else (100.5, 101.0)
    open_price = kw.pop("open_price", open_price)
    base = dict(reclaim_level=level, reclaim_atr=2.0)
    base.update(kw)
    store, mgr = _env(make(**base), [open_price])
    assert _tr(mgr.poll(OPEN)) == ["gap_reclaim_order"]
    return store, mgr


def _step(store, mgr, price, now):
    return mgr._step(store.get("p1"), price, now)


def test_the_phase_table_points_at_the_reclaim_handlers():
    assert pm._MARKET_PHASE_STEPS[mo.WAITING] == "_market_waiting"
    assert pm._MARKET_PHASE_STEPS[mo.AFTER_CLOSE] == "_market_after_close"


@pytest.mark.parametrize("make, touch, through", [(_bull, 100.0, 100.01), (_bear, 100.0, 99.99)])
def test_the_reclaim_fills_at_e_only_one_tick_through_it(make, touch, through):
    store, mgr = _resting(make)
    assert _step(store, mgr, touch, _et(14, 10)) == []        # a bare touch of E is not a fill
    assert store.get("p1").status == PlanStatus.PENDING
    events = _step(store, mgr, through, _et(14, 10, 1))
    assert _tr(events) == ["filled"]
    assert events[0].detail == {"entry_price": 100.0, "live_price": through, "fill": "reclaim"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.ACTIVE and plan.entry_price == 100.0
    assert plan.status_history[-1]["reason"] == "gap_reclaim_fill"


def test_a_sub_dollar_reclaim_uses_the_small_tick():
    store, mgr = _resting(trigger_price=0.85, stop_loss=0.835, tp1=0.88, tp2=0.9,
                          reclaim_level=0.84, open_price=0.84)
    assert _step(store, mgr, 0.85005, _et(14, 10)) == []
    assert _tr(_step(store, mgr, 0.8501, _et(14, 10, 1))) == ["filled"]
    assert store.get("p1").entry_price == 0.85


def test_the_reclaim_fill_moves_the_placeholder_to_e():
    log = _Log()
    plan = _bull(reclaim_level=99.5, reclaim_atr=2.0)
    feed = FakePriceFeed()
    feed.set_series("AAPL", [99.0, 100.01])
    store = PlanStore()
    store.add(plan)
    mgr = PlanManager(store, feed.get_price, trade_log=log)
    mgr.poll(OPEN)
    mgr.poll(_et(14, 10))
    assert ("fill", "p1", 100.0) in log.calls
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_a_print_through_the_stop_while_resting_cancels_nothing():
    store, mgr = _resting()
    assert _step(store, mgr, 98.0, _et(14, 11)) == []
    assert store.get("p1").status == PlanStatus.PENDING
    assert _tr(_step(store, mgr, 100.01, _et(14, 14))) == ["filled"]


def test_the_open_decision_is_never_taken_twice():
    store, mgr = _resting()
    assert _step(store, mgr, 99.0, _et(14, 11)) == []           # still at or beyond X
    assert store.get("p1").reclaim_session == "2026-10-14"


@pytest.mark.parametrize("now", [_et(14, 16), _et(14, 17, 30), _et(15, 9, 45)])
def test_no_reclaim_by_the_close_cancels(now):
    store, mgr = _resting()
    events = _step(store, mgr, 99.2, now)
    assert _tr(events) == ["cancelled_gap_no_reclaim"]
    assert events[0].detail == {"entry_price": 100.0, "session": "2026-10-14"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.CANCELLED and plan.entry_price is None
    assert plan.status_history[-1]["reason"] == "gap_no_reclaim"
    assert plan.status_history[-1]["at"] == "2026-10-14T16:00:00-04:00"


def test_a_bearish_plan_cancels_the_same_way():
    store, mgr = _resting(_bear)
    assert _tr(_step(store, mgr, 100.8, _et(14, 16, 5))) == ["cancelled_gap_no_reclaim"]


def test_a_restart_keeps_the_rest_and_still_cancels_at_the_close():
    store, _mgr = _resting()
    before = store.get("p1")
    fresh = PlanManager(PlanStore(), lambda ticker: 99.0)        # a restarted bot
    plan = fresh.store.get("p1")
    assert (plan.reclaim_session, plan.reclaim_level, plan.reclaim_atr) == (
        before.reclaim_session, before.reclaim_level, before.reclaim_atr) == ("2026-10-14", 99.5, 2.0)
    assert fresh._step(plan, 99.0, _et(14, 12)) == []
    assert _tr(fresh._step(fresh.store.get("p1"), 99.0, _et(14, 16, 1))) == [
        "cancelled_gap_no_reclaim"]


def test_a_knob_flip_while_resting_changes_nothing(monkeypatch):
    store, mgr = _resting()
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.0)
    assert _tr(_step(store, mgr, 100.01, _et(14, 10))) == ["filled"]
    assert store.get("p1").entry_price == 100.0
