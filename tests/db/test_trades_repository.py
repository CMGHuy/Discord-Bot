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


def _trade(trade_id, **overrides):
    trade = {
        "trade_id": trade_id, "ticker": "MSFT", "strategy": "swing",
        "horizon": "swing", "direction": "long", "status": "open",
        "opened_at": "2026-01-02T15:00:00+00:00",
    }
    trade.update(overrides)
    return trade


def test_open_and_closed_trades_partition_the_table(db_conn):
    repository = TradeRepository()
    repository.insert(_trade("T-1"), conn=db_conn)
    repository.insert(_trade("T-2", status="win", closed_at="2026-01-09T15:00:00+00:00"), conn=db_conn)
    assert [row["trade_id"] for row in repository.open_trades(conn=db_conn)] == ["T-1"]
    assert [row["trade_id"] for row in repository.closed_trades(conn=db_conn)] == ["T-2"]


def test_has_open_requires_every_trade_dimension(db_conn):
    repository = TradeRepository()
    repository.insert(_trade("T-1"), conn=db_conn)
    assert repository.has_open("msft", "swing", "swing", "long", conn=db_conn)
    assert not repository.has_open("MSFT", "swing", "swing", "short", conn=db_conn)


def test_clear_filters_by_trade_status(db_conn):
    repository = TradeRepository()
    repository.insert(_trade("T-1"), conn=db_conn)
    repository.insert(_trade("T-2", status="win", closed_at="2026-01-09T15:00:00+00:00"), conn=db_conn)
    assert repository.clear(status="open", conn=db_conn) == 1
    assert repository.count(conn=db_conn) == 1


def test_every_part2_table_exists_and_is_registered():
    from swingbot.core.db import schema

    for name in ("plans", "starred_plans", "account", "account_balance_history",
                 "journal_entries", "signal_state", "watchlist"):
        assert name in schema.METADATA.tables, name
        assert name in schema.PROMOTED, name
