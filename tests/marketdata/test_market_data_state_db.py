"""market_data_state is a table (v116)."""
import pytest

from swingbot import config
from swingbot.core.db.repositories.market_data_state import MarketDataStateRepository
from swingbot.core.marketdata import data_refresh

STATE = {"AAPL|daily": {"last_status": "failed", "fail_count": 2, "last_error": "timeout"}}


def test_save_state_writes_the_table(store_db):
    data_refresh.save_state(STATE)
    assert MarketDataStateRepository().load(conn=store_db) == STATE
    assert data_refresh.load_state() == STATE
    assert data_refresh.pending_gaps() == [("AAPL", "daily", 2, "timeout")]


def test_the_table_starts_empty_without_an_import(store_db):
    assert data_refresh.load_state() == {}


@pytest.mark.real_engine
def test_an_unreachable_database_never_breaks_a_refresh(monkeypatch):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/none")
    reset_engine()
    try:
        data_refresh.save_state(STATE)
        assert data_refresh.load_state() == {}
    finally:
        reset_engine()
