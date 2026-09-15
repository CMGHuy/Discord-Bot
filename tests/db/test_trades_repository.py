"""Trade repository declaration-level contracts independent of a live DB."""
from swingbot.core.db.repositories.trades import TradeRepository, trades_repo
from swingbot.core.db.schema import trades


def test_trade_repository_uses_the_trade_id_public_key():
    repository = TradeRepository()
    assert repository.table is trades
    assert repository.key == "trade_id"
    assert repository.key_col is trades.c.trade_id


def test_trade_repository_accessor_is_process_local_singleton():
    assert trades_repo() is trades_repo()


def test_trade_repository_round_trips_and_patches_a_document_field(db_conn):
    repository = TradeRepository()
    repository.insert({
        "trade_id": "DB-T1", "ticker": "AAPL", "strategy": "RSI", "horizon": "2w",
        "direction": "bullish", "status": "open", "opened_at": "2026-01-02T15:00:00+00:00",
        "confidence": 4,
    }, conn=db_conn)

    updated = repository.patch("DB-T1", {"exit_reason": "TP1"}, conn=db_conn)

    assert updated["confidence"] == 4
    assert updated["exit_reason"] == "TP1"
    assert repository.open_for_ticker("aapl", conn=db_conn)["trade_id"] == "DB-T1"
