"""The kill switch engages automatically and releases only by hand."""
import os

import pytest

from swingbot import config
from swingbot.core.edge import throttle


@pytest.fixture(params=["", "killswitch:dual", "killswitch:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "killswitch.json"))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()
    return request.param


def test_default_state_is_disengaged(any_stage):
    assert throttle.kill_state().get("on") is False


def test_engage_then_read_back(any_stage):
    throttle.set_kill(True, reason="drawdown")
    state = throttle.kill_state()
    assert state["on"] is True and state["reason"] == "drawdown"


def test_release(any_stage):
    throttle.set_kill(True, reason="drawdown")
    throttle.set_kill(False, reason="manual")
    assert throttle.kill_state()["on"] is False


def test_engaging_twice_keeps_the_first_reason(any_stage):
    throttle.set_kill(True, reason="drawdown")
    throttle.set_kill(True, reason="spy_move")
    assert throttle.kill_state()["reason"] == "drawdown"


def test_auto_trigger_never_overrides_a_manual_release(any_stage):
    throttle.set_kill(True, reason="drawdown")
    throttle.set_kill(False, reason="manual")
    throttle.set_kill(True, reason="spy_move")
    assert throttle.kill_state()["on"] is False


def test_no_killswitch_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "killswitch:db":
        pytest.skip("file absence is only asserted at the db stage")
    throttle.set_kill(True, reason="drawdown")
    assert not os.path.exists(tmp_path / "killswitch.json")
