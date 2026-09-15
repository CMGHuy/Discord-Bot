"""Whole-file reloads are deliberately inert once TradeLog reads rows."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.infra.jsonio import atomic_write_json
from swingbot.core.tracking.performance import TradeLog


def _record(trade_id):
    return {"trade_id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon": "2w",
            "direction": "bullish", "status": "open", "opened_at": "2026-01-02T15:00:00+00:00"}


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_engine):
    from swingbot.core.db import engine as db_engine_module
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    db_engine_module.reset_engine()
    yield tmp_path
    db_engine_module.reset_engine()


def test_long_lived_instance_sees_new_rows_without_reload(db_stage):
    log = TradeLog()
    assert log.get_trades(status="open", limit=None) == []
    TradeRepository().upsert(_record("LATER"))
    assert [row["id"] for row in log.get_trades(status="open", limit=None)] == ["LATER"]


def test_reload_and_refresh_ignore_a_file_at_the_db_stage(db_stage):
    log = TradeLog()
    atomic_write_json(os.path.join(db_stage, "trades.json"), [{"id": "GHOST"}])
    log.reload()
    log.refresh()
    assert log._trades == []


def test_reload_still_reads_a_file_at_the_json_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "")
    log = TradeLog()
    atomic_write_json(os.path.join(tmp_path, "trades.json"), [{"id": "FROMFILE"}])
    log.reload()
    assert [row["id"] for row in log._trades] == ["FROMFILE"]
