"""The kill switch engages automatically and releases only by hand."""
import pytest

from swingbot import config
from swingbot.core.edge import throttle


@pytest.fixture
def db_ready(monkeypatch, db_committed, db_engine):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def test_default_state_is_disengaged(db_ready):
    assert throttle.kill_state().get("on") is False


def test_engage_then_read_back(db_ready):
    throttle.set_kill(True, reason="drawdown")
    state = throttle.kill_state()
    assert state["on"] is True and state["reason"] == "drawdown"


def test_release(db_ready):
    throttle.set_kill(True, reason="drawdown")
    throttle.set_kill(False, reason="manual")
    assert throttle.kill_state()["on"] is False


def test_engaging_twice_keeps_the_first_reason(db_ready):
    throttle.set_kill(True, reason="drawdown")
    throttle.set_kill(True, reason="spy_move")
    assert throttle.kill_state()["reason"] == "drawdown"


def test_auto_trigger_never_overrides_a_manual_release(db_ready):
    throttle.set_kill(True, reason="drawdown")
    throttle.set_kill(False, reason="manual")
    throttle.set_kill(True, reason="spy_move")
    assert throttle.kill_state()["on"] is False
