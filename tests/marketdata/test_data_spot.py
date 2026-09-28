"""v109: data.py never hands back unscaled futures for a spot metal."""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import data as data_mod
from swingbot.core.marketdata import spot_metals as sm
from swingbot.core.marketdata.providers import router

READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, 4151.70 / 4175.30)
QUOTE = sm.SpotQuote(4151.70, datetime(2026, 9, 28, 9, 45, tzinfo=timezone.utc))


def _frame(close=4000.0):
    return pd.DataFrame({"Open": [close], "High": [close], "Low": [close],
                         "Close": [close], "Volume": [10.0]},
                        index=pd.DatetimeIndex(["2026-09-25"]))


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", False)
    router.reset()
    data_mod._price_cache.clear()
    data_mod._last_good_batch_price.clear()

    def no_yahoo(*a, **k):
        raise AssertionError("a spot metal reached a direct Yahoo call")
    monkeypatch.setattr(data_mod.yf_safe, "download", no_yahoo)
    monkeypatch.setattr(data_mod.yf, "Ticker", no_yahoo)
    yield
    router.reset()
    data_mod._price_cache.clear()
    data_mod._last_good_batch_price.clear()


def _batch(calls):
    def fetch(tickers, period):
        calls.append(list(tickers))
        return {t: _frame() for t in tickers if t in ("GC=F", "AAPL")}
    return fetch


def test_single_daily_is_the_scaled_future(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (READING, ""))
    calls = []
    monkeypatch.setattr(data_mod, "_yf_daily_batch", _batch(calls))
    df = data_mod.get_daily_data("xauusd")
    assert calls == [["GC=F"]]
    assert df["Close"].iloc[-1] == pytest.approx(4000.0 * READING.ratio)
    assert df.attrs["source"] == "spot-scaled:GC=F"


def test_single_daily_outage_raises_never_aliases(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    monkeypatch.setattr(data_mod, "_yf_daily_batch", _batch([]))
    with pytest.raises(ValueError, match="spot quote missing"):
        data_mod.get_daily_data("XAUUSD")


def test_batch_daily_returns_spot_under_its_own_name(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (READING, ""))
    calls = []
    monkeypatch.setattr(data_mod, "_yf_daily_batch", _batch(calls))
    out = data_mod.get_daily_data_batch(["AAPL", "XAUUSD"])
    assert calls == [["AAPL"], ["GC=F"]]
    assert set(out) == {"AAPL", "XAUUSD"}
    assert out["XAUUSD"].attrs["source"] == "spot-scaled:GC=F"


def test_batch_daily_outage_is_absent(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    monkeypatch.setattr(data_mod, "_yf_daily_batch", _batch([]))
    assert data_mod.get_daily_data_batch(["XAUUSD"]) == {}


def test_price_detail_is_the_spot_quote(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (QUOTE, ""))
    assert data_mod.get_current_price_detail("XAUUSD", allow_stale=False) == \
        data_mod.PriceQuote(4151.70, False)
    assert data_mod.get_current_price("XAUUSD", allow_stale=False) == 4151.70


def test_price_detail_outage(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (None, "spot quote missing"))
    assert data_mod.get_current_price_detail("XAUUSD", allow_stale=False) is None
    data_mod._price_cache["XAUUSD"] = (4150.0, 0.0, False)
    assert data_mod.get_current_price_detail("XAUUSD", allow_stale=False) is None
    assert data_mod.get_current_price_detail("XAUUSD", allow_stale=True) == \
        data_mod.PriceQuote(4150.0, True)


def test_batch_price_is_the_spot_quote(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (QUOTE, ""))
    asked = []
    monkeypatch.setattr(data_mod, "_yf_batch_prices",
                        lambda ts: asked.append(list(ts)) or {"AAPL": 190.0})
    out = data_mod.get_current_price_batch(["XAUUSD", "AAPL"], allow_stale=False)
    assert asked == [["AAPL"]]
    assert out == {"XAUUSD": 4151.70, "AAPL": 190.0}
    assert router.last_source("XAUUSD") == "spot"


def test_batch_price_outage_is_absent_for_trading(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (None, "spot quote missing"))
    monkeypatch.setattr(data_mod, "_yf_batch_prices", lambda ts: pytest.fail("no yfinance"))
    assert data_mod.get_current_price_batch(["XAUUSD"], allow_stale=False) == {}


def test_not_found_hint_names_the_spot_symbols(monkeypatch):
    monkeypatch.setattr(data_mod.yf_safe, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(ValueError) as err:
        data_mod.get_daily_data("NOPE1")
    assert "XAUUSD" in str(err.value) and "XAGUSD" in str(err.value)


def test_watchlist_help_names_the_spot_symbols():
    text = (Path(__file__).resolve().parents[2] / "swingbot" / "commands" / "watchlist.py").read_text(
        encoding="utf-8")
    assert "gold = `XAUUSD`" in text and "silver = `XAGUSD`" in text
