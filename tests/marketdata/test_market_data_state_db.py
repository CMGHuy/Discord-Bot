"""market_data_state at each stage (v116 Phase 1)."""
import json
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.market_data_state import MarketDataStateRepository
from swingbot.core.marketdata import data_refresh

STATE = {"AAPL|daily": {"last_status": "failed", "fail_count": 2, "last_error": "timeout"}}


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    path = tmp_path / "market_data_state.json"
    monkeypatch.setattr(data_refresh, "STATE_FILE", str(path))
    return path


def test_json_stage_uses_only_the_file(state_file, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    data_refresh.save_state(STATE)
    assert json.loads(state_file.read_text()) == STATE
    assert data_refresh.load_state() == STATE


def test_dual_writes_both_and_reads_the_file(state_file, store_db, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "market_data_state:dual")
    data_refresh.save_state(STATE)
    assert json.loads(state_file.read_text()) == STATE
    assert MarketDataStateRepository().load(conn=store_db) == STATE


def test_db_stage_uses_only_the_table(state_file, store_db, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "market_data_state:db")
    data_refresh.save_state(STATE)
    assert not os.path.exists(state_file)
    assert data_refresh.load_state() == STATE
    assert data_refresh.pending_gaps() == [("AAPL", "daily", 2, "timeout")]


def test_db_stage_starts_empty_without_an_import(state_file, store_db, monkeypatch):
    state_file.write_text(json.dumps(STATE))
    monkeypatch.setattr(config, "DB_STORES", "market_data_state:db")
    assert data_refresh.load_state() == {}


def test_an_unreachable_database_never_breaks_a_refresh(state_file, monkeypatch):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DB_STORES", "market_data_state:db")
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/none")
    reset_engine()
    try:
        data_refresh.save_state(STATE)
        assert data_refresh.load_state() == {}
    finally:
        reset_engine()
