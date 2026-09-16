"""Same trades on two backends must produce the same analytics."""
import os

import pytest

from swingbot import config
from swingbot.core.analytics.snapshots import build_snapshot
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.infra.jsonio import atomic_write_json
from swingbot.core.tracking.performance import TradeLog, _db_record


def _closed(index, status, r_multiple):
    return dict(
        id=f"T{index}", ticker=["AAPL", "MSFT", "NVDA"][index % 3],
        strategy=["RSI", "MACD"][index % 2], horizon_key="2w",
        direction="bullish" if index % 2 else "bearish", status=status,
        opened_at=f"2026-01-{(index % 27) + 1:02d}T15:00:00+00:00",
        closed_at=f"2026-02-{(index % 27) + 1:02d}T15:00:00+00:00",
        entry=100.0 + index, stop_loss=95.0 + index, take_profit=110.0 + index,
        confidence_level=(index % 5) + 1, r_multiple=r_multiple,
        realized_pnl_amount=r_multiple * 100.0, exit_price=100.0 + index + r_multiple,
    )


@pytest.fixture
def population():
    return [_closed(i, "win" if i % 3 else "loss", 2.0 if i % 3 else -1.0)
            for i in range(40)]


@pytest.fixture
def db_url(db_engine, monkeypatch):
    monkeypatch.setattr(
        config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False)
    )
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def _snapshot_from(trade_log):
    closed = [trade for trade in trade_log.get_trades(status=None, limit=None)
              if trade.get("status") in ("win", "loss")]
    snapshot = build_snapshot(closed, starting_balance=10000.0, registry_entries=[])
    snapshot.pop("built_at", None)  # runtime metadata, not an analytics result
    return snapshot


def _seed_db(rows):
    repo = TradeRepository()
    for row in rows:
        repo.upsert(_db_record(row))


def test_snapshots_are_identical_across_backends(population, tmp_path, monkeypatch,
                                                 db_committed, db_url):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "")
    atomic_write_json(os.path.join(tmp_path, "trades.json"), population)
    from_file = _snapshot_from(TradeLog())

    _seed_db(population)
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    assert _snapshot_from(TradeLog()) == from_file


def test_extended_stats_are_identical_across_backends(population, tmp_path, monkeypatch,
                                                       db_committed, db_url):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "")
    atomic_write_json(os.path.join(tmp_path, "trades.json"), population)
    file_stats = TradeLog().get_extended_stats()

    _seed_db(population)
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    assert TradeLog().get_extended_stats() == file_stats


def test_confidence_stats_are_identical_across_backends(population, tmp_path, monkeypatch,
                                                         db_committed, db_url):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "")
    atomic_write_json(os.path.join(tmp_path, "trades.json"), population)
    file_stats = TradeLog().get_stats_by_confidence()

    _seed_db(population)
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    assert TradeLog().get_stats_by_confidence() == file_stats
