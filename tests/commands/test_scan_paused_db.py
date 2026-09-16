"""Pause and manual-trigger flags across storage stages."""
import os

import pytest

from swingbot import config
from swingbot.commands.scanning import runstate


@pytest.fixture(params=["", "flags:dual", "flags:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()
    return request.param


def test_pause_then_resume(any_stage):
    assert not runstate.is_scan_paused()
    runstate.set_scan_paused(True)
    assert runstate.is_scan_paused()
    runstate.set_scan_paused(False)
    assert not runstate.is_scan_paused()


def test_trigger_request_and_clear(any_stage):
    assert not runstate.is_trigger_requested()
    runstate.request_trigger()
    assert runstate.is_trigger_requested()
    runstate.clear_trigger()
    assert not runstate.is_trigger_requested()


def test_no_flag_files_at_db_stage(any_stage, tmp_path):
    if any_stage != "flags:db":
        pytest.skip("file absence is only a db-stage property")
    runstate.set_scan_paused(True)
    runstate.request_trigger()
    assert not os.path.exists(tmp_path / "scan_paused.flag")
    assert not os.path.exists(tmp_path / "trigger_check.flag")
