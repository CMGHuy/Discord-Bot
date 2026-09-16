"""The heartbeat is the one store allowed to swallow a write failure."""
import os

import pytest

from swingbot import config
from swingbot.commands.scanning import runstate
from swingbot.core.db.repositories.heartbeat import HeartbeatRepository


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(tmp_path / "bot_heartbeat.json"))
    return tmp_path


@pytest.fixture
def db_url(db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def test_json_stage_writes_the_file(data_dir, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    runstate._write_heartbeat()
    assert os.path.exists(data_dir / "bot_heartbeat.json")


def test_db_stage_writes_a_row(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "heartbeat:db")
    runstate._write_heartbeat()
    last = HeartbeatRepository().last(conn=db_committed)
    assert last is not None and "ts" in last
    assert "session_active" in last and "scan_paused" in last


def test_beating_twice_keeps_one_row(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "heartbeat:db")
    runstate._write_heartbeat()
    runstate._write_heartbeat()
    assert HeartbeatRepository().count(conn=db_committed) == 1


def test_the_timestamp_advances(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "heartbeat:db")
    runstate._write_heartbeat()
    first = HeartbeatRepository().last(conn=db_committed)["ts"]
    runstate._write_heartbeat()
    assert HeartbeatRepository().last(conn=db_committed)["ts"] >= first


def test_a_database_failure_does_not_take_down_the_scan_loop(data_dir, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "heartbeat:db")
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine

    dbengine.reset_engine()
    runstate._write_heartbeat()
    dbengine.reset_engine()


def test_last_is_none_on_an_empty_table(db_conn):
    assert HeartbeatRepository().last(conn=db_conn) is None
