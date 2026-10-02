"""Scan run state is the flags table."""
import pytest

from swingbot import config
from swingbot.core.scanning import runstate


@pytest.fixture
def db_ready(monkeypatch, db_committed, db_engine):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def test_stop_is_not_requested_initially(db_ready):
    assert runstate.is_stop_requested() is False


def test_request_then_clear(db_ready):
    runstate.request_stop()
    assert runstate.is_stop_requested() is True
    runstate._clear_stop()
    assert runstate.is_stop_requested() is False


def test_clearing_twice_is_not_an_error(db_ready):
    runstate._clear_stop()
    runstate._clear_stop()


def test_mark_running_toggles(db_ready):
    assert runstate.is_scan_running() is False
    runstate._mark_running(True)
    assert runstate.is_scan_running() is True
    runstate._mark_running(False)
    assert runstate.is_scan_running() is False
