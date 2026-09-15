"""The open-P/L report must share one live-price request across positions."""
from swingbot.core.scanning import scan_run


def _trade(trade_id, ticker):
    return {
        "id": trade_id, "ticker": ticker, "entry": 100.0, "stop_loss": 95.0,
        "take_profit": 110.0, "direction": "bullish",
    }


def test_all_unrealized_pnl_uses_one_distinct_ticker_batch(monkeypatch):
    trades = [_trade("one", "AAPL"), _trade("two", "AAPL"), _trade("three", "MSFT")]
    calls = []

    class Log:
        def get_trades(self, **_kwargs):
            return trades

    monkeypatch.setattr(scan_run, "trade_log", Log())
    monkeypatch.setattr(
        scan_run.fetch, "get_current_price_batch",
        lambda tickers: calls.append(tickers) or {"AAPL": 101.0, "MSFT": 102.0},
    )
    monkeypatch.setattr(
        scan_run.fetch, "get_daily_data",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("daily fallback")),
    )

    rows = scan_run.get_all_unrealized_pnl()

    assert calls == [["AAPL", "MSFT"]]
    assert len(rows) == 3
    assert [row["pnl"].pct_change for row in rows] == [1.0, 1.0, 2.0]
