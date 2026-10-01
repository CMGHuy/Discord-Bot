"""TradeLog writes normalized rows to the trades table."""
import pytest

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.tracking.performance import TradeLog, _db_record


def _log_one(log):
    return log.log_trade(ticker="AAPL", strategy="RSI", horizon_key="2w",
                         direction="bullish", confidence_level=4,
                         confidence_label="Strong", entry=100.0, stop_loss=95.0,
                         take_profit=110.0)


def test_log_trade_round_trips_through_the_table():
    log = TradeLog()
    trade_id = _log_one(log)
    stored = TradeRepository().get(trade_id)
    assert stored is not None and stored["ticker"] == "AAPL"
    from tests.db_diff import diff_records
    trade = log.get_trade_by_id(trade_id)
    assert diff_records(_db_record(trade), stored) == []


@pytest.mark.real_engine
def test_database_failure_raises(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as db_engine
    db_engine.reset_engine()
    with pytest.raises(db_engine.DatabaseUnavailable):
        _log_one(TradeLog())
    db_engine.reset_engine()


def test_close_updates_and_delete_removes_the_row():
    log = TradeLog()
    trade_id = _log_one(log)
    log.close_trade_manual(trade_id, reason="test")
    assert TradeRepository().get(trade_id)["status"] != "open"
    log.delete_trade(trade_id)
    assert TradeRepository().get(trade_id) is None
