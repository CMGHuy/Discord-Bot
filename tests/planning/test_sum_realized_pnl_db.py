"""Realized P&L must read rows after the trades cutover."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.planning.account import _sum_realized_pnl


def _closed(trade_id, pnl):
    return dict(trade_id=trade_id, ticker="AAPL", strategy="RSI", horizon="2w",
                direction="bullish", status="win",
                opened_at="2026-01-02T15:00:00+00:00",
                closed_at="2026-01-09T15:00:00+00:00",
                realized_pnl_amount=pnl)


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    monkeypatch.setattr(
        config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False)
    )
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def test_realized_pnl_sums_rows_at_the_db_stage(db_stage):
    TradeRepository().upsert(_closed("T1", 100.0))
    TradeRepository().upsert(_closed("T2", -40.0))
    assert _sum_realized_pnl() == pytest.approx(60.0)


def test_an_open_trade_is_not_counted(db_stage):
    TradeRepository().upsert(_closed("T1", 100.0))
    TradeRepository().upsert(dict(
        trade_id="T2", ticker="AAPL", strategy="RSI", horizon="2w",
        direction="bullish", status="open", opened_at="2026-01-02T15:00:00+00:00"))
    assert _sum_realized_pnl() == pytest.approx(100.0)


def test_an_explicit_path_still_reads_that_file(db_stage, tmp_path):
    from swingbot.core.infra.jsonio import atomic_write_json
    TradeRepository().upsert(_closed("INDB", 999.0))
    path = os.path.join(tmp_path, "other_trades.json")
    atomic_write_json(path, [_closed("INFILE", 5.0)])
    assert _sum_realized_pnl(trades_path=path) == pytest.approx(5.0)


def test_a_missing_realized_amount_is_rederived_from_legs(db_stage):
    TradeRepository().upsert(dict(
        trade_id="T1", ticker="AAPL", strategy="RSI", horizon="2w",
        direction="bullish", status="win",
        opened_at="2026-01-02T15:00:00+00:00",
        closed_at="2026-01-09T15:00:00+00:00",
        entry=100.0, stop_loss=95.0, shares=10.0,
        legs=[{"fraction": 1.0, "exit_price": 110.0, "r": 2.0}]))
    assert _sum_realized_pnl() != 0.0
