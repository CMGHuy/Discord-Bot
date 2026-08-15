from swingbot.core.tracking.performance import TradeLog


def test_get_trades_sort_by_confidence_handles_none_level(tmp_path):
    """A Plan Engine v2 auto-filled trade logs confidence_level=None
    (see plan_manager.py's `_on_event`, transition == "filled"). Sorting
    by confidence must not crash when it's mixed with trades that do
    have a numeric level."""
    log = TradeLog(path=str(tmp_path / "trades.json"))
    log.log_trade(ticker="AAPL", strategy="RSI", horizon_key="4w",
                   direction="bullish", confidence_level=None,
                   confidence_label=None, entry=100.0, stop_loss=95.0,
                   take_profit=110.0)
    log.log_trade(ticker="MSFT", strategy="MACD", horizon_key="4w",
                   direction="bullish", confidence_level=4,
                   confidence_label="Strong", entry=200.0, stop_loss=190.0,
                   take_profit=220.0)

    trades = log.get_trades(status="open", limit=None, sort_by="confidence")

    assert [t["ticker"] for t in trades] == ["MSFT", "AAPL"]
