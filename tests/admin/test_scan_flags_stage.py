"""The admin's scan trigger and pause go through the bot's runstate module.

The bot reads `runtime_flags`. An admin that wrote its own flags elsewhere
would queue a scan nothing ever runs and show a pause the bot never obeys --
silently, on both sides.
"""
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
    yield admin_app.test_client()
    reset_engine()


def test_pause_and_resume_move_the_row_the_bot_reads(client_at, auth):
    client = client_at

    body = client.post("/api/v1/system/scan/pause", headers=auth).get_json()
    assert body["scan"]["paused"] is True
    assert body["scan"]["paused_at"] is not None
    assert runstate.is_scan_paused() is True

    body = client.post("/api/v1/system/scan/resume", headers=auth).get_json()
    assert body["scan"]["paused"] is False
    assert runstate.is_scan_paused() is False


def test_trigger_sets_the_row_the_bot_reads(client_at, auth):
    client = client_at

    body = client.post("/api/v1/system/scan/trigger", headers=auth).get_json()
    assert body["scan"]["pending"] is True
    assert body["scan"]["triggered_at"] is not None
    assert runstate.is_trigger_requested() is True
