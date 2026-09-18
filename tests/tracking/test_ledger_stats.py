import pytest

from swingbot import config
from swingbot.core.tracking.performance import TradeLog


@pytest.fixture
def log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return TradeLog(path=str(tmp_path / "trades.json"))


def _open(log, ticker, ledger=None):
    return log.log_trade(ticker=ticker, strategy="MACD", horizon_key="3m", direction="bullish",
                         confidence_level=None, confidence_label="strategy signal", entry=100.0,
                         stop_loss=95.0, take_profit=110.0, source="strategy", badge="WEAK", ledger=ledger)


def _close(log, trade_id, status, pnl):
    trade = log.get_trade_by_id(trade_id)
    trade.update(status=status, exit_price=100.0, realized_pnl_amount=pnl,
                 closed_at="2026-09-17T20:00:00+00:00")
    log._save()


def test_ledger_scopes_records_stats_and_summary(log):
    main = _open(log, "AAPL")
    weak_loss = _open(log, "MSFT", ledger="weak")
    weak_win = _open(log, "NVDA", ledger="weak")
    _close(log, main, "win", 100.0)
    _close(log, weak_loss, "loss", -50.0)
    _close(log, weak_win, "win", 80.0)
    assert log.get_trade_by_id(main)["ledger"] == "main"
    assert log.get_stats()["closed"] == 1
    assert log.get_stats(ledger="weak")["closed"] == 2
    assert log.get_stats(ledger=None)["closed"] == 3
    assert {t["ticker"] for t in log.get_trades(status="open", limit=None, ledger="weak")} == set()
    assert log.weak_summary()["total_pnl"] == 30.0
