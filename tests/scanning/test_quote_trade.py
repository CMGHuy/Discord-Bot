"""v170: !pnl's per-trade body, extracted so the P&L-now button prices one
trade exactly the way !pnl prices it (spec §3, A5, A6)."""
import datetime as dt

import pandas as pd

from swingbot.core.planning.account import compute_unrealized_pnl
from swingbot.core.scanning import scan_run

TRADE = {"id": "t1", "ticker": "AAPL", "entry": 100.0, "stop_loss": 95.0,
         "take_profit": 110.0, "direction": "bullish"}
BAR_DAY = dt.date(2026, 10, 15)


def _no_daily(monkeypatch):
    monkeypatch.setattr(
        scan_run.fetch, "get_daily_data",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("daily fallback")))


def _daily(monkeypatch, closes):
    calls = []
    index = pd.date_range(end=pd.Timestamp(BAR_DAY), periods=len(closes), freq="D")

    def fake(ticker, period="2y"):
        calls.append((ticker, period))
        return pd.DataFrame({"Close": closes}, index=index)

    monkeypatch.setattr(scan_run.fetch, "get_daily_data", fake)
    return calls


def _daily_fails(monkeypatch):
    def fail(*_a, **_k):
        raise RuntimeError("yfinance down")
    monkeypatch.setattr(scan_run.fetch, "get_daily_data", fail)


def test_a_live_batch_price_marks_the_trade_with_no_daily_close(monkeypatch):
    _no_daily(monkeypatch)
    quote, pnl = scan_run.unrealized_for_trade(TRADE, {"AAPL": 101.0}, {})
    assert quote == scan_run.TradeQuote(price=101.0, daily_close=None)
    assert pnl == compute_unrealized_pnl(entry=100.0, stop_loss=95.0, take_profit=110.0,
                                         direction="bullish", current_price=101.0)


def test_a_missing_live_price_falls_back_to_the_daily_close_and_dates_it(monkeypatch):
    calls = _daily(monkeypatch, [99.0, 102.0])
    cache, dates = {}, {}
    quote, pnl = scan_run.unrealized_for_trade(TRADE, cache, dates)
    assert quote == scan_run.TradeQuote(price=102.0, daily_close=BAR_DAY)
    assert pnl.pct_change == 2.0
    assert calls == [("AAPL", "5d")]
    assert cache == {"AAPL": 102.0} and dates == {"AAPL": BAR_DAY}


def test_a_second_trade_on_the_same_ticker_reuses_the_cached_daily_close(monkeypatch):
    calls = _daily(monkeypatch, [99.0, 102.0])
    cache, dates = {}, {}
    scan_run.unrealized_for_trade(TRADE, cache, dates)
    quote, _pnl = scan_run.unrealized_for_trade(dict(TRADE, id="t2"), cache, dates)
    assert calls == [("AAPL", "5d")]
    assert quote == scan_run.TradeQuote(price=102.0, daily_close=BAR_DAY)


def test_no_price_anywhere_is_a_quote_without_a_price_never_an_exception(monkeypatch):
    _daily_fails(monkeypatch)
    quote, pnl = scan_run.unrealized_for_trade(TRADE, {}, {})
    assert quote == scan_run.TradeQuote(price=None) and pnl is None


def test_an_empty_daily_frame_is_no_price(monkeypatch):
    monkeypatch.setattr(scan_run.fetch, "get_daily_data",
                        lambda *_a, **_k: pd.DataFrame({"Close": []}))
    quote, pnl = scan_run.unrealized_for_trade(TRADE, {}, {})
    assert quote.price is None and pnl is None


def test_quote_trade_asks_a_one_ticker_batch(monkeypatch):
    calls = []
    monkeypatch.setattr(scan_run.fetch, "get_current_price_batch",
                        lambda tickers: calls.append(tickers) or {"AAPL": 104.0})
    _no_daily(monkeypatch)
    quote, pnl = scan_run.quote_trade(TRADE)
    assert calls == [["AAPL"]]
    assert quote == scan_run.TradeQuote(price=104.0) and pnl.pct_change == 4.0


def test_quote_trade_survives_a_failed_batch_and_a_failed_daily_fetch(monkeypatch):
    def fail(_tickers):
        raise TimeoutError("batch down")
    monkeypatch.setattr(scan_run.fetch, "get_current_price_batch", fail)
    _daily_fails(monkeypatch)
    assert scan_run.quote_trade(TRADE) == (scan_run.TradeQuote(price=None), None)


def test_all_unrealized_pnl_still_skips_a_trade_with_no_price(monkeypatch):
    trades = [TRADE, dict(TRADE, id="t2", ticker="MSFT")]

    class Log:
        def get_trades(self, **_kwargs):
            return trades

    monkeypatch.setattr(scan_run, "trade_log", Log())
    monkeypatch.setattr(scan_run.fetch, "get_current_price_batch",
                        lambda tickers: {"AAPL": 101.0})
    _daily_fails(monkeypatch)
    rows = scan_run.get_all_unrealized_pnl()
    assert [row["trade"]["id"] for row in rows] == ["t1"]
    assert rows[0]["pnl"].pct_change == 1.0
