"""v106: data.py's live-path fetches go through the provider router when
ALPACA_ENABLED is on -- Alpaca for eligible US symbols, today's yfinance code
for everything else and for every Alpaca miss."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import data as data_mod
from swingbot.core.marketdata.providers import router

_FIELDS = ["Open", "High", "Low", "Close", "Volume"]
_DAYS = pd.DatetimeIndex(["2026-09-24", "2026-09-25"])


def _alpaca_frame():
    return pd.DataFrame(7.0, index=_DAYS, columns=pd.Index(_FIELDS))


class FakeProvider:
    def __init__(self, daily=(), prices=None):
        self.daily, self.prices = set(daily), prices or {}

    def daily_bars(self, tickers, period):
        return {t: _alpaca_frame() for t in tickers if t in self.daily}

    def latest_prices(self, tickers, max_age):
        return {t: p for t, p in self.prices.items() if t in tickers}

    def intraday_bars(self, t, iv):
        return None


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", True)
    monkeypatch.setattr(config, "ALPACA_API_KEY_ID", "k")
    monkeypatch.setattr(config, "ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setattr(data_mod, "_price_cache", {})
    monkeypatch.setattr(data_mod, "_last_good_batch_price", {})
    router.reset()
    yield
    router.reset()


def _use(monkeypatch, prov):
    monkeypatch.setattr(router, "_provider_factory", lambda *a: prov)


def _no_yf_download(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("yf.download must not be called")
    monkeypatch.setattr(data_mod.yf, "download", boom)


def test_batch_splits_alpaca_and_yfinance(monkeypatch):
    _use(monkeypatch, FakeProvider(daily={"AAPL"}))
    asked = []

    def fake(arg, **k):
        asked.append(arg)
        cols = pd.MultiIndex.from_product([["SAP.DE"], _FIELDS])
        return pd.DataFrame(1.0, index=_DAYS, columns=cols)
    monkeypatch.setattr(data_mod.yf, "download", fake)
    out = data_mod.get_daily_data_batch(["AAPL", "SAP.DE"])
    assert asked == ["SAP.DE"]
    assert out["AAPL"].attrs["source"] == "alpaca"
    assert out["SAP.DE"].attrs["source"] == "yfinance"
    assert out["AAPL"]["Close"].iloc[-1] == 7.0


def test_single_daily_alpaca_hit_skips_yfinance(monkeypatch):
    _use(monkeypatch, FakeProvider(daily={"AAPL"}))
    _no_yf_download(monkeypatch)
    out = data_mod.get_daily_data("AAPL")
    assert out.attrs["source"] == "alpaca"


def test_single_daily_index_goes_to_candidate_loop(monkeypatch):
    _use(monkeypatch, FakeProvider(daily={"^GSPC"}))
    asked = []

    def fake(sym, **k):
        asked.append(sym)
        return _alpaca_frame()
    monkeypatch.setattr(data_mod.yf, "download", fake)
    data_mod.get_daily_data("^GSPC")
    assert asked == ["^GSPC"]


def test_single_daily_alpaca_miss_runs_candidate_loop(monkeypatch):
    _use(monkeypatch, FakeProvider())
    asked = []

    def fake(sym, **k):
        asked.append(sym)
        return _alpaca_frame()
    monkeypatch.setattr(data_mod.yf, "download", fake)
    data_mod.get_daily_data("AAPL")
    assert asked == ["AAPL"]


def test_price_batch_alpaca_hit_updates_last_good(monkeypatch):
    _use(monkeypatch, FakeProvider(prices={"AAPL": 190.0}))
    _no_yf_download(monkeypatch)
    assert data_mod.get_current_price_batch(["AAPL"], allow_stale=False) == {"AAPL": 190.0}
    assert data_mod._last_good_batch_price["AAPL"][0] == 190.0


def test_price_detail_alpaca_hit(monkeypatch):
    _use(monkeypatch, FakeProvider(prices={"AAPL": 190.0}))

    class NoTicker:
        def __init__(self, sym):
            raise AssertionError("yf.Ticker must not be called")
    monkeypatch.setattr(data_mod.yf, "Ticker", NoTicker)
    assert data_mod.get_current_price_detail("AAPL", allow_stale=False) == \
        data_mod.PriceQuote(190.0, False)
    assert data_mod._price_cache["AAPL"][0] == 190.0


def test_price_detail_alpaca_miss_uses_history(monkeypatch):
    _use(monkeypatch, FakeProvider())

    class FakeTicker:
        def __init__(self, sym):
            pass

        def history(self, **k):
            return pd.DataFrame({"Close": [55.0]})
    monkeypatch.setattr(data_mod.yf, "Ticker", FakeTicker)
    assert data_mod.get_current_price_detail("AAPL", allow_stale=False) == \
        data_mod.PriceQuote(55.0, False)
