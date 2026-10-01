"""The admin's scan trigger and pause go through the bot's runstate module.

At `flags:db` the bot reads `runtime_flags`, not the flag files in data/. An
admin that wrote its own files there would queue a scan nothing ever runs and
show a pause the bot never obeys -- silently, on both sides.
"""
import json
import os

import pytest

from swingbot import config
from swingbot.commands.scanning import runstate


@pytest.fixture
def client_at(admin_app, monkeypatch, db_committed):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(
        config, "DATABASE_URL",
        db_committed.engine.url.render_as_string(hide_password=False))
    reset_engine()
    client = admin_app.test_client()

    def _make(stage):
        monkeypatch.setattr(config, "DB_STORES", stage)
        return client
    yield _make
    reset_engine()


def _flag_files(directory):
    return sorted(name for name in os.listdir(directory) if name.endswith(".flag"))


def test_db_stage_pause_and_resume_move_the_row_the_bot_reads(client_at, auth, tmp_path):
    client = client_at("flags:db")

    body = client.post("/api/v1/system/scan/pause", headers=auth).get_json()
    assert body["scan"]["paused"] is True
    assert body["scan"]["paused_at"] is not None
    assert runstate.is_scan_paused() is True

    body = client.post("/api/v1/system/scan/resume", headers=auth).get_json()
    assert body["scan"]["paused"] is False
    assert runstate.is_scan_paused() is False
    assert _flag_files(tmp_path) == []


def test_db_stage_trigger_sets_the_row_the_bot_reads(client_at, auth, tmp_path):
    client = client_at("flags:db")

    body = client.post("/api/v1/system/scan/trigger", headers=auth).get_json()
    assert body["scan"]["pending"] is True
    assert body["scan"]["triggered_at"] is not None
    assert runstate.is_trigger_requested() is True
    assert _flag_files(tmp_path) == []


def test_json_stage_trigger_file_keeps_the_admin_payload(client_at, auth, tmp_path):
    """Byte-compatible with the pre-routing admin: the file carries the
    admin's JSON body, not runstate's bare timestamp."""
    client = client_at("")

    body = client.post("/api/v1/system/scan/trigger", headers=auth).get_json()
    assert body["scan"]["pending"] is True
    assert body["scan"]["triggered_at"] is not None
    assert runstate._TRIGGER_FILE == str(tmp_path / "trigger_check.flag")
    with open(runstate._TRIGGER_FILE) as fh:
        payload = json.load(fh)
    assert payload["source"] == "admin_ui"
    assert set(payload) == {"triggered_at", "source"}


def test_json_stage_pause_writes_the_file_the_bot_polls(client_at, auth, tmp_path):
    client = client_at("")

    body = client.post("/api/v1/system/scan/pause", headers=auth).get_json()
    assert body["scan"]["paused_at"] is not None
    assert runstate._PAUSE_FILE == str(tmp_path / "scan_paused.flag")
    assert runstate.is_scan_paused() is True
