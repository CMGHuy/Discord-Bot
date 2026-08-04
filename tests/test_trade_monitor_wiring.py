import os

import swingbot.config as config
from swingbot.core import plan_manager as pm


def test_flag_off_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", False)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    pm._MANAGER = None                       # reset the singleton
    assert pm.run_manager_tick() == []
    assert not os.path.exists(tmp_path / "plans.json")   # not even created


def test_flag_on_polls_open_plans(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    pm._MANAGER = None
    from swingbot.core.plan_store import PlanStore
    from tests.test_plan_manager_pending import _pending
    PlanStore().add(_pending())
    monkeypatch.setattr(pm, "_price_fn", lambda t: 106.0)   # injectable feed
    # Same treatment for the OTHER live feed this tick pulls on. The real
    # _bars_since calls get_daily_data(ticker) and counts real trading bars
    # since the plan's created_at -- so with the fixture's fixed 2026-07-11
    # date and expiry_bars=5, this test started passing and then silently
    # became a permanent failure once the wall clock moved ~5 trading days
    # past that, asserting "filled" against a plan the manager was right to
    # cancel as expired. It also reached for real market data to do it.
    # A fresh pending plan is the precondition this test means to set up,
    # not something to leave to the calendar; expiry itself is covered by
    # test_plan_manager_pending.py.
    monkeypatch.setattr(pm, "_bars_since", lambda ticker, created_at: 0)
    events = pm.run_manager_tick()
    assert [e.transition for e in events] == ["filled"]
