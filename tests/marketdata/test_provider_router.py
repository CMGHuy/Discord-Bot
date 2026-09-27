import time
import pandas as pd
import pytest
from swingbot import config
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaAuthError, AlpacaMiss

def _df():
    return pd.DataFrame({"Close": [1.0]}, index=pd.DatetimeIndex(["2026-09-25"]))

class FakeProvider:
    def __init__(self, daily=None, prices=None, exc=None, sleep=0):
        self.daily, self.prices, self.exc, self.sleep, self.calls = daily or {}, prices or {}, exc, sleep, 0
    def _maybe(self):
        self.calls += 1
        if self.sleep: time.sleep(self.sleep)
        if self.exc: raise self.exc
    def daily_bars(self, tickers, period):
        self._maybe(); return {t: _df() for t in tickers if t in self.daily}
    def latest_prices(self, tickers, max_age):
        self._maybe(); return {t: p for t, p in self.prices.items() if t in tickers}
    def intraday_bars(self, t, iv):
        self._maybe(); return None

@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", True)
    monkeypatch.setattr(config, "ALPACA_API_KEY_ID", "k")
    monkeypatch.setattr(config, "ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setattr(config, "ALPACA_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(config, "ALPACA_BREAKER_FAILURES", 2)
    monkeypatch.setattr(config, "ALPACA_BREAKER_COOLDOWN_SECONDS", 60)
    router.reset()
    yield
    router.reset()

def _use(monkeypatch, prov):
    monkeypatch.setattr(router, "_provider_factory", lambda *a: prov)

def yf_daily(calls):
    def f(tickers, period):
        calls.append(list(tickers)); return {t: _df() for t in tickers}
    return f

def test_disabled_is_pure_yfinance(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", False); router.reset()
    prov = FakeProvider(daily={"AAPL"}); _use(monkeypatch, prov); calls = []
    out = router.daily_bars(["AAPL"], "2y", yf_daily(calls))
    assert prov.calls == 0 and calls == [["AAPL"]]
    assert out["AAPL"].attrs["source"] == "yfinance"

def test_split_by_eligibility(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider(daily={"AAPL"})); calls = []
    out = router.daily_bars(["AAPL", "SAP.DE"], "2y", yf_daily(calls))
    assert calls == [["SAP.DE"]]
    assert out["AAPL"].attrs["source"] == "alpaca"
    assert out["SAP.DE"].attrs["source"] == "yfinance"

def test_partial_alpaca_result_falls_back_per_symbol(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider(daily={"AAPL"})); calls = []
    out = router.daily_bars(["AAPL", "MSFT"], "2y", yf_daily(calls))
    assert calls == [["MSFT"]]
    assert out["MSFT"].attrs["source"] == "yfinance-fallback"

def test_timeout_falls_back(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider(daily={"AAPL"}, sleep=2)); calls = []
    t0 = time.monotonic()
    out = router.daily_bars(["AAPL"], "2y", yf_daily(calls))
    assert time.monotonic() - t0 < 1.5
    assert out["AAPL"].attrs["source"] == "yfinance-fallback"

def test_breaker_opens_then_cools_down(enabled, monkeypatch):
    prov = FakeProvider(exc=AlpacaMiss("500")); _use(monkeypatch, prov)
    for _ in range(3):
        router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 2 and router.stats()["breaker_open"] is True
    monkeypatch.setattr(router._breaker, "open_until", 0.0)
    router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 3

def test_auth_error_latches_until_keys_change(enabled, monkeypatch):
    prov = FakeProvider(exc=AlpacaAuthError("401")); _use(monkeypatch, prov)
    router.daily_bars(["AAPL"], "2y", yf_daily([]))
    monkeypatch.setattr(router._breaker, "open_until", 0.0)
    router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 1                      # latched, not cooled down
    monkeypatch.setattr(config, "ALPACA_API_KEY_ID", "k2")
    prov.exc = None
    router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 2                      # new keys -> new client, latch cleared

def test_latest_prices_records_last_source(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider(prices={"AAPL": 190.0}))
    out = router.latest_prices(["AAPL", "SAP.DE"], lambda ts: {t: 50.0 for t in ts})
    assert out == {"AAPL": 190.0, "SAP.DE": 50.0}
    assert router.last_source("AAPL") == "alpaca"
    assert router.last_source("SAP.DE") == "yfinance"

def test_bucket_exhausted_is_a_miss(enabled, monkeypatch):
    prov = FakeProvider(daily={"AAPL"}); _use(monkeypatch, prov)
    monkeypatch.setattr(router._bucket, "tokens", 0.0)
    monkeypatch.setattr(router._bucket, "refill_per_s", 0.0)
    out = router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 0 and out["AAPL"].attrs["source"] == "yfinance-fallback"

def test_non_hourly_intraday_is_plain_yfinance(enabled, monkeypatch):
    prov = FakeProvider(); _use(monkeypatch, prov)
    out = router.intraday_bars("AAPL", "15m", lambda t, iv: _df())
    assert prov.calls == 0 and out.attrs["source"] == "yfinance"
