"""v109: the router splits spot metals off before Alpaca/yfinance."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import spot_metals as sm
from swingbot.core.marketdata.providers import router

READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, 4151.70 / 4175.30)
SILVER = sm.SpotRatio("XAGUSD", 48.0, "SI=F", 48.4, 48.0 / 48.4)
QUOTE = sm.SpotQuote(4151.70, datetime(2026, 9, 28, 9, 45, tzinfo=timezone.utc))


def _frame(close=4000.0):
    return pd.DataFrame({"Open": [close], "High": [close], "Low": [close],
                         "Close": [close], "Volume": [10.0]},
                        index=pd.DatetimeIndex(["2026-09-25"]))


@pytest.fixture(autouse=True)
def _plain(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", False)
    router.reset()
    yield
    router.reset()


def _ratio_ok(monkeypatch):
    table = {"XAUUSD": READING, "XAGUSD": SILVER}
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (table[s], ""))


def _yf_daily(calls, have=("AAPL", "GC=F", "SI=F")):
    def fetch(tickers, period):
        calls.append(list(tickers))
        return {t: _frame() for t in tickers if t in have}
    return fetch


def test_daily_spot_is_scaled_future_and_never_asked_by_name(monkeypatch):
    _ratio_ok(monkeypatch)
    calls = []
    out = router.daily_bars(["AAPL", "XAUUSD"], "2y", _yf_daily(calls))
    assert calls == [["AAPL"], ["GC=F"]]
    assert set(out) == {"AAPL", "XAUUSD"}
    assert out["XAUUSD"]["Close"].iloc[-1] == pytest.approx(4000.0 * READING.ratio)
    assert out["XAUUSD"].attrs["source"] == "spot-scaled:GC=F"
    assert out["AAPL"].attrs["source"] == "yfinance"


def test_daily_reuses_a_future_the_same_call_fetched(monkeypatch):
    _ratio_ok(monkeypatch)
    calls = []
    out = router.daily_bars(["GC=F", "XAUUSD", "XAGUSD"], "2y", _yf_daily(calls))
    assert calls == [["GC=F"], ["SI=F"]]
    assert out["GC=F"]["Close"].iloc[-1] == 4000.0          # the raw future, unscaled
    assert out["GC=F"].attrs["source"] == "yfinance"
    assert set(out) == {"GC=F", "XAUUSD", "XAGUSD"}


def test_daily_spot_only_call(monkeypatch):
    _ratio_ok(monkeypatch)
    calls = []
    out = router.daily_bars(["XAUUSD"], "2y", _yf_daily(calls))
    assert calls == [["GC=F"]] and list(out) == ["XAUUSD"]


def test_daily_outage_drops_the_spot_symbol_and_records_why(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    out = router.daily_bars(["XAUUSD"], "2y", _yf_daily([]))
    assert out == {}
    assert router.spot_miss_reason("xauusd") == "spot quote missing"


def test_daily_missing_future_bars(monkeypatch):
    _ratio_ok(monkeypatch)
    out = router.daily_bars(["XAUUSD"], "2y", _yf_daily([], have=()))
    assert out == {} and router.spot_miss_reason("XAUUSD") == "no GC=F bars"


def test_a_later_hit_clears_the_miss(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    router.daily_bars(["XAUUSD"], "2y", _yf_daily([]))
    _ratio_ok(monkeypatch)
    router.daily_bars(["XAUUSD"], "2y", _yf_daily([]))
    assert router.spot_miss_reason("XAUUSD") is None


def test_latest_prices_serve_the_spot_quote(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (QUOTE, ""))
    asked = []
    out = router.latest_prices(["AAPL", "XAUUSD"],
                               lambda ts: asked.append(list(ts)) or {"AAPL": 190.0})
    assert asked == [["AAPL"]]
    assert out == {"AAPL": 190.0, "XAUUSD": 4151.70}
    assert router.last_source("XAUUSD") == "spot"
    assert router.last_source("AAPL") == "yfinance"


def test_latest_prices_outage_is_absent_never_futures(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (None, "spot quote stale (1200s old)"))
    out = router.latest_prices(["XAUUSD"], lambda ts: pytest.fail("no yfinance call"))
    assert out == {}
    assert router.spot_miss_reason("XAUUSD") == "spot quote stale (1200s old)"


def test_intraday_spot_scales_the_future(monkeypatch):
    _ratio_ok(monkeypatch)
    asked = []
    df = router.intraday_bars("XAUUSD", "1h", lambda t, iv: asked.append((t, iv)) or _frame())
    assert asked == [("GC=F", "1h")]
    assert df.attrs["source"] == "spot-scaled:GC=F"
    assert df["Close"].iloc[-1] == pytest.approx(4000.0 * READING.ratio)


def test_intraday_outage_is_none(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    assert router.intraday_bars("XAUUSD", "1h", lambda t, iv: _frame()) is None


def test_reset_clears_spot_misses(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    router.daily_bars(["XAUUSD"], "2y", _yf_daily([]))
    router.reset()
    assert router.spot_miss_reason("XAUUSD") is None
