"""Scan run state at every persistence stage."""
import pytest

from swingbot import config
from swingbot.core.scanning import runstate


@pytest.fixture(params=["", "flags:dual", "flags:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()
    return request.param


def test_stop_is_not_requested_initially(any_stage):
    assert runstate.is_stop_requested() is False


def test_request_then_clear(any_stage):
    runstate.request_stop()
    assert runstate.is_stop_requested() is True
    runstate._clear_stop()
    assert runstate.is_stop_requested() is False


def test_clearing_twice_is_not_an_error(any_stage):
    runstate._clear_stop()
    runstate._clear_stop()


def test_mark_running_toggles(any_stage):
    assert runstate.is_scan_running() is False
    runstate._mark_running(True)
    assert runstate.is_scan_running() is True
    runstate._mark_running(False)
    assert runstate.is_scan_running() is False
