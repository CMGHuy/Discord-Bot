"""Phase 4 harness: every store is Postgres, so every test reaches the test
database through the app's own engine, and seeds stores through importers."""
from swingbot.core.db import engine as engine_module
from swingbot.core.db.repositories.trades import TradeRepository
from tests.store_seed import seed_store

TRADE = {"id": "T1", "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
         "direction": "bullish", "status": "open", "opened_at": "2026-10-01T10:00:00+00:00",
         "entry": 100.0, "stop_loss": 98.0}


def test_the_app_engine_is_the_test_database_without_asking():
    with engine_module.get_engine().connect() as conn:
        assert conn.exec_driver_sql("select current_database()").scalar().startswith("swingbot_test")


def test_seed_store_writes_through_the_real_importer():
    seed_store("trades", [TRADE])
    assert TradeRepository().get("T1")["ticker"] == "AAPL"


def test_the_previous_test_left_nothing_behind():
    assert TradeRepository().count() == 0


def test_get_engine_is_the_lazy_test_fixture():
    assert engine_module.get_engine.__name__ == "lazy"
