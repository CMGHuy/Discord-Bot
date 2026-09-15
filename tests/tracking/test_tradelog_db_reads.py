"""The db stage reads normalized rows through TradeLog's compatibility seam."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.tracking.performance import TradeLog


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_engine):
    from swingbot.core.db import engine as db_engine_module
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    db_engine_module.reset_engine()
    yield tmp_path
    db_engine_module.reset_engine()


def test_db_stage_reads_rows_in_the_existing_json_api_shape(db_stage):
    TradeRepository().upsert({
        "trade_id": "T1", "ticker": "AAPL", "strategy": "RSI", "horizon": "2w",
        "direction": "bullish", "status": "open", "opened_at": "2026-01-02T15:00:00+00:00",
        "entry": 100.0, "stop_loss": 95.0,
    })
    log = TradeLog()
    trade = log.get_trade_by_id("T1")
    assert trade["id"] == "T1" and trade["horizon_key"] == "2w"
    assert isinstance(trade["entry"], float) and trade["entry"] - trade["stop_loss"] == 5.0
    assert not os.path.exists(db_stage / "trades.json")
