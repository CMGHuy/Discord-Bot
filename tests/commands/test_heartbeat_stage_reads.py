"""At heartbeat:db the counter, the alert flag and the admin read the row (v116)."""
import pytest

from swingbot import config
from swingbot.commands.scanning import runstate


@pytest.fixture
def at_db(tmp_path, store_db, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(tmp_path / "bot_heartbeat.json"))
    monkeypatch.setattr(config, "DB_STORES", "heartbeat:db")
    return tmp_path


def test_the_failure_counter_counts_at_the_db_stage(at_db):
    assert runstate.record_tick_failure() == 1
    assert runstate.record_tick_failure() == 2
    runstate.set_alert_active(True)
    assert runstate.get_alert_active() is True
    assert runstate.record_tick_success() is True
    assert runstate._read_heartbeat()["consecutive_failures"] == 0
    assert not (at_db / "bot_heartbeat.json").exists()


def test_the_admin_reads_the_row_at_the_db_stage(at_db):
    from swingbot.admin import app as admin_app
    runstate._write_heartbeat()
    runstate.record_tick_failure()
    payload = admin_app.scan_status_payload()
    assert payload["bot_alive"] is True
    assert payload["bot_consecutive_failures"] == 1
    assert payload["bot_last_seen"] is not None


def test_the_json_stage_still_reads_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(tmp_path / "bot_heartbeat.json"))
    monkeypatch.setattr(config, "DB_STORES", "")
    runstate.record_tick_failure()
    assert runstate.record_tick_failure() == 2
    assert (tmp_path / "bot_heartbeat.json").exists()
