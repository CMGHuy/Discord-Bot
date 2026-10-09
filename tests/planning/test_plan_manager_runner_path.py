"""v142: every runner close stamps runner_path (source "live"); a stamp that
cannot be computed leaves it null and never blocks the close."""
import pytest

from swingbot.core.analytics import runner_path as rp
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_engine import PlanStatus, runner_floor
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.analytics.test_runner_path import FILL, LONG_BARS, MON, WED
from tests.planning.test_plan_engine_model import _plan


def _partial():
    """Entry 100, risk 5, TP1 (110) banked MON at 2.0R, runner open on the floor."""
    return _plan(entry_price=100.0, stop_loss=95.0, tp1=110.0, tp2=120.0,
                 status=PlanStatus.PARTIAL, working_stop=runner_floor(100.0, 110.0),
                 legs_realized=[{"fraction": 0.5, "exit_price": 110.0, "r": 2.0,
                                 "reason": "tp1", "closed_at": MON}],
                 status_history=[{"status": "ACTIVE", "reason": "filled", "at": FILL},
                                 {"status": "PARTIAL", "reason": "tp1_partial", "at": MON}])


def _manager(bars_fn):
    store = PlanStore()
    store.add(_partial())
    mgr = PlanManager(store, lambda ticker: None, runner_bars_fn=bars_fn)
    mgr._now = lambda: WED                      # the runner exits on WED
    return store, mgr


def test_a_floor_close_on_the_bar_path_stamps_live():
    store, mgr = _manager(lambda ticker: LONG_BARS)
    [event] = mgr.check_bar("p1", 107.0, 108.0, 106.0)
    assert event.detail["reason"] == "tp1_runner_be"
    path = store.get("p1").runner_path
    # A floor exit: WED's 121 high is not counted; TUE's 116 is the best.
    assert (path["source"], path["mfe_r"], path["ladder"]["4.0"]) == ("live", 3.2, None)


def test_a_tp2_close_counts_the_exit_session_bar():
    store, mgr = _manager(lambda ticker: LONG_BARS)
    [event] = mgr.check_bar("p1", 118.0, 121.0, 115.0)
    assert event.detail["reason"] == "tp1_runner_tp2"
    path = store.get("p1").runner_path
    assert (path["mfe_r"], path["ladder"]["4.0"]) == (4.2, "2026-10-07")


@pytest.mark.parametrize("reason", ["tp1_runner_trail", "tp1_runner_progress_stall", "time_exit"])
def test_every_runner_close_reason_stamps(reason):
    store, mgr = _manager(lambda ticker: LONG_BARS)
    mgr._close_runner(store.get("p1"), 113.0, reason, 5.0, 1)
    plan = store.get("p1")
    assert plan.status == PlanStatus.CLOSED
    assert plan.runner_path["source"] == "live" and plan.runner_path["sessions_after_tp1"] == 2


def test_missing_bars_close_the_plan_with_a_null_stamp():
    store, mgr = _manager(lambda ticker: None)
    mgr.check_bar("p1", 107.0, 108.0, 106.0)
    plan = store.get("p1")
    assert plan.status == PlanStatus.CLOSED and len(plan.legs_realized) == 2
    assert plan.runner_path is None


def test_a_failing_bar_source_never_blocks_the_close():
    def boom(ticker):
        raise OSError("cache unreadable")

    store, mgr = _manager(boom)
    mgr.check_bar("p1", 107.0, 108.0, 106.0)
    assert store.get("p1").status == PlanStatus.CLOSED
    assert store.get("p1").runner_path is None


def test_no_bar_source_configured_stamps_null():
    store, mgr = _manager(None)
    mgr.check_bar("p1", 107.0, 108.0, 106.0)
    assert store.get("p1").runner_path is None


def test_the_production_manager_reads_the_disk_cache(monkeypatch):
    monkeypatch.setattr(pm, "_MANAGER", None)
    assert pm._manager().runner_bars_fn is rp.cached_daily_bars
