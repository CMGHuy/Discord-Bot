import pytest

import os

import swingbot.config as config
from swingbot.core.planning import plan_manager as pm


def test_flag_off_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", False)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    pm._MANAGER = None                       # reset the singleton
    assert pm.run_manager_tick() == []
    assert not os.path.exists(tmp_path / "plans.json")   # not even created


def test_flag_on_polls_open_plans(tmp_path, monkeypatch):
    """Flag on: the tick builds the manager and polls open plans.

    This is a WIRING test -- it asserts that `run_manager_tick()` reaches
    `PlanManager.poll()` at all. It is not a test of expiry, which
    `test_plan_manager_pending.py` owns.

    **Both external inputs are injected, and the bar count has to be.** It was
    quarantined `xfail` for months as "wall-clock dependent", which undersold
    it: the shared `_pending()` fixture is created at a fixed `2026-07-11`
    with `expiry_bars=5`, while `_bars_since` counts REAL trading days from a
    real `get_daily_data()` fetch. Once five trading days had passed the plan
    expired to `cancelled_expired` before it could fill, so the test did not
    fail intermittently -- it failed permanently, and drifted further from
    passing every day. `strict=False` then hid that behind an `xfail` that
    could never become an `xpass`.

    Injecting `_bars_since` fixes the cause rather than the symptom, and
    matches how `_price_fn` was already handled two lines below. It also drops
    a live data fetch from the test.
    """
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    pm._MANAGER = None
    from swingbot.core.planning.plan_store import PlanStore
    from tests.planning.test_plan_manager_pending import _pending
    PlanStore().add(_pending())
    monkeypatch.setattr(pm, "_price_fn", lambda t: 106.0)   # injectable feed
    # Fresh plan: no bars have elapsed, so expiry is not what is under test.
    monkeypatch.setattr(pm, "_bars_since", lambda ticker, created_at: 0)
    events = pm.run_manager_tick()
    assert [e.transition for e in events] == ["filled"]


def test_flag_on_still_expires_a_stale_pending_plan(tmp_path, monkeypatch):
    """The other half of the seam the test above injects.

    Pinning it here means the injected bar count cannot quietly become a way
    of never exercising expiry through `run_manager_tick()` at all.
    """
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    pm._MANAGER = None
    from swingbot.core.planning.plan_store import PlanStore
    from tests.planning.test_plan_manager_pending import _pending
    PlanStore().add(_pending())
    monkeypatch.setattr(pm, "_price_fn", lambda t: 106.0)
    # Past its 5-bar window: expiry wins even though price crossed the trigger.
    monkeypatch.setattr(pm, "_bars_since", lambda ticker, created_at: 6)
    events = pm.run_manager_tick()
    assert [e.transition for e in events] == ["cancelled_expired"]

def test_run_manager_tick_is_a_no_op_outside_regular_hours(monkeypatch, tmp_path):
    from swingbot import config
    from swingbot.core.planning import plan_manager
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(plan_manager, "_MANAGER", None)
    monkeypatch.setattr(plan_manager, "is_regular_session", lambda now=None: False)
    assert plan_manager.run_manager_tick() == []

@pytest.fixture(autouse=True)
def _rth_gate_off(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, 'INTRADAY_RTH_ONLY', False)
