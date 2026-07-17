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
    events = pm.run_manager_tick()
    assert [e.transition for e in events] == ["filled"]
