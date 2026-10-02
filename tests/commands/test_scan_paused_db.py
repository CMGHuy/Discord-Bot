"""Pause and manual-trigger flags are rows in the flags table."""
import pytest

from swingbot import config
from swingbot.commands.scanning import runstate


@pytest.fixture
def db_ready(monkeypatch, db_committed, db_engine):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def test_pause_then_resume(db_ready):
    assert not runstate.is_scan_paused()
    runstate.set_scan_paused(True)
    assert runstate.is_scan_paused()
    runstate.set_scan_paused(False)
    assert not runstate.is_scan_paused()


def test_trigger_request_and_clear(db_ready):
    assert not runstate.is_trigger_requested()
    runstate.request_trigger()
    assert runstate.is_trigger_requested()
    runstate.clear_trigger()
    assert not runstate.is_trigger_requested()
