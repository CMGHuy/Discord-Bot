"""TradeLog keeps the JSON source while dual-writing a normalized shadow."""
import json
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.tracking.performance import TradeLog, _db_record


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def _log_one(log):
    return log.log_trade(ticker="AAPL", strategy="RSI", horizon_key="2w",
                         direction="bullish", confidence_level=4,
                         confidence_label="Strong", entry=100.0, stop_loss=95.0,
                         take_profit=110.0)


def _file_trades(data_dir):
    path = os.path.join(data_dir, "trades.json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []


@pytest.fixture
def db_url(db_engine, monkeypatch):
    """Point repository-owned connections at the disposable test database."""
    from swingbot.core.db import engine as db_engine_module
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    db_engine_module.reset_engine()
    yield
    db_engine_module.reset_engine()


def test_json_stage_writes_only_the_file(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    _log_one(TradeLog())
    assert len(_file_trades(data_dir)) == 1
    assert TradeRepository().count(conn=db_conn) == 0


def test_dual_stage_writes_and_round_trips(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "trades:dual")
    log = TradeLog()
    trade_id = _log_one(log)
    assert len(_file_trades(data_dir)) == 1
    stored = TradeRepository().get(trade_id, conn=db_committed)
    assert stored is not None and stored["ticker"] == "AAPL"
    from swingbot.core.db.dual import diff_records
    trade = next(row for row in log._trades if row["id"] == trade_id)
    assert diff_records(_db_record(trade), stored) == []


def test_dual_stage_still_reads_from_the_file(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "trades:dual")
    log = TradeLog()
    _log_one(log)
    TradeRepository().clear(conn=db_committed)
    db_committed.commit()
    assert len(TradeLog().get_trades(status="open", limit=None)) == 1


def test_database_failure_at_dual_stage_raises(data_dir, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "trades:dual")
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as db_engine
    db_engine.reset_engine()
    with pytest.raises(db_engine.DatabaseUnavailable):
        _log_one(TradeLog())
    db_engine.reset_engine()


def test_dual_stage_updates_and_deletes_the_row(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "trades:dual")
    log = TradeLog()
    trade_id = _log_one(log)
    log.close_trade_manual(trade_id, reason="test")
    assert TradeRepository().get(trade_id, conn=db_committed)["status"] != "open"
    log.delete_trade(trade_id)
    assert TradeRepository().get(trade_id, conn=db_committed) is None
