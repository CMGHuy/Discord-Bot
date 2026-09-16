"""JournalStore at each storage stage."""
import os

import pytest

from swingbot import config
from swingbot.core.analytics.journal import JournalStore
from swingbot.core.db.repositories.journal import JournalRepository


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def db_url(db_engine, monkeypatch):
    monkeypatch.setattr(
        config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False)
    )
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def _entry(trade_id="T1", **overrides):
    entry = dict(trade_id=trade_id, strategy="RSI", outcome="win",
                 closed_at="2026-01-09T15:00:00+00:00", tags=["runner"],
                 note="", lesson="held to TP1")
    entry.update(overrides)
    return entry


def test_json_stage_is_unchanged(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    JournalStore().add(_entry())
    assert os.path.exists(os.path.join(data_dir, "journal.json"))
    assert JournalRepository().count(conn=db_conn) == 0


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "journal:dual")
    JournalStore().add(_entry())
    assert os.path.exists(os.path.join(data_dir, "journal.json"))
    assert JournalRepository().get("T1", conn=db_committed) is not None


def test_db_stage_reads_rows_without_a_file(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "journal:db")
    store = JournalStore()
    store.add(_entry("T1"))
    store.add(_entry("T2", outcome="loss"))
    assert {entry["trade_id"] for entry in store.entries()} == {"T1", "T2"}
    assert [entry["trade_id"] for entry in store.entries(outcome="loss")] == ["T2"]
    assert not os.path.exists(os.path.join(data_dir, "journal.json"))


def test_add_stamps_created_at_every_time(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "journal:db")
    store = JournalStore()
    first = store.add(_entry())
    second = store.add(_entry(lesson="revised"))
    assert second["created_at"] >= first["created_at"]
    assert store.get("T1")["lesson"] == "revised"


def test_add_returns_stamped_entry_and_missing_get_is_none(data_dir, monkeypatch,
                                                           db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "journal:db")
    out = JournalStore().add(_entry())
    assert "created_at" in out and out["trade_id"] == "T1"
    assert JournalStore().get("nope") is None
