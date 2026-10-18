import time
import pandas as pd
import pytest
from swingbot import config
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaAuthError, AlpacaMiss

def _df():
    return pd.DataFrame({"Close": [1.0]}, index=pd.DatetimeIndex(["2026-09-25"]))

class FakeProvider:
    def __init__(self, daily=None, prices=None, exc=None, sleep=0, quotes=None):
        self.daily, self.prices, self.exc, self.sleep, self.calls = daily or {}, prices or {}, exc, sleep, 0
        self.quotes = quotes or {}
    def _maybe(self):
        self.calls += 1
        if self.sleep: time.sleep(self.sleep)
        if self.exc: raise self.exc
    def daily_bars(self, tickers, period):
        self._maybe(); return {t: _df() for t in tickers if t in self.daily}
    def daily_bars_between(self, tickers, start, end):
        self._maybe(); self.between = (list(tickers), start, end)
        return {t: _df() for t in tickers if t in self.daily}
    def latest_prices(self, tickers, max_age):
        self._maybe(); return {t: p for t, p in self.prices.items() if t in tickers}
    def latest_quotes(self, tickers, max_age):
        self._maybe(); return {t: q for t, q in self.quotes.items() if t in tickers}
    def intraday_bars(self, t, iv):
        self._maybe(); return None

@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", True)
    monkeypatch.setattr(config, "ALPACA_API_KEY_ID", "k")
    monkeypatch.setattr(config, "ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setattr(config, "ALPACA_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(config, "ALPACA_BARS_TIMEOUT_SECONDS", 0.5)
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
    assert prov.calls == 4 and router.stats()["breaker_open"] is True  # 2 calls x (try + 1 retry)
    monkeypatch.setattr(router._breaker, "open_until", 0.0)
    router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 6

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


class BatchProvider(FakeProvider):
    """Records each daily_bars batch; raises for a batch holding `bad`."""
    def __init__(self, bad=None, **kw):
        super().__init__(**kw); self.batches, self.bad = [], bad
    def daily_bars(self, tickers, period):
        self.batches.append(list(tickers))
        if self.bad in tickers: raise AlpacaMiss("boom")
        self._maybe(); return {t: _df() for t in tickers}

def _syms(n): return [f"A{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(n)]

def _size(monkeypatch, n):
    monkeypatch.setattr(router, "symbols_per_request", lambda period: n)

def test_daily_bars_sends_page_sized_batches(enabled, monkeypatch):
    prov = BatchProvider(); _use(monkeypatch, prov); _size(monkeypatch, 20)
    tickers = _syms(45)
    out = router.daily_bars(tickers, "2y", yf_daily([]))
    assert sorted(len(b) for b in prov.batches) == [5, 20, 20]
    assert {out[t].attrs["source"] for t in tickers} == {"alpaca"}

def test_failed_batch_falls_back_only_its_symbols(enabled, monkeypatch):
    tickers = _syms(45)
    prov = BatchProvider(bad=tickers[25]); _use(monkeypatch, prov); _size(monkeypatch, 20)
    calls = []
    out = router.daily_bars(tickers, "2y", yf_daily(calls))
    assert calls == [tickers[20:40]]
    assert {out[t].attrs["source"] for t in tickers[:20] + tickers[40:]} == {"alpaca"}
    assert {out[t].attrs["source"] for t in tickers[20:40]} == {"yfinance-fallback"}

def test_batches_run_in_parallel_under_one_deadline(enabled, monkeypatch):
    prov = BatchProvider(sleep=0.3); _use(monkeypatch, prov); _size(monkeypatch, 2)
    tickers = _syms(6); t0 = time.monotonic()
    out = router.daily_bars(tickers, "2y", yf_daily([]))
    assert time.monotonic() - t0 < 0.5
    assert {out[t].attrs["source"] for t in tickers} == {"alpaca"}

def test_each_batch_takes_a_bucket_token(enabled, monkeypatch):
    prov = BatchProvider(); _use(monkeypatch, prov); _size(monkeypatch, 2)
    router._bucket.tokens, router._bucket.refill_per_s = 2.0, 0.0
    tickers = _syms(6); calls = []
    out = router.daily_bars(tickers, "2y", yf_daily(calls))
    assert len(prov.batches) == 2 and calls == [tickers[4:]]
    assert {out[t].attrs["source"] for t in tickers[4:]} == {"yfinance-fallback"}

def test_miss_log_names_timeout(enabled, monkeypatch, caplog):
    _use(monkeypatch, FakeProvider(daily={"AAPL"}, sleep=2)); caplog.set_level("DEBUG")
    router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert "TimeoutError" in caplog.text


from datetime import datetime, timezone
from swingbot.core.marketdata.shared.kinds import QuoteDetail

_T = datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc)


def _q(sym, price, source="alpaca-iex", bid=None, ask=None):
    return QuoteDetail(symbol=sym, price=price, trade_at=_T if price else None,
                       bid=bid, ask=ask, quote_at=_T if bid else None, source=source)


def yf_quotes(calls, prices):
    def f(tickers):
        calls.append(list(tickers))
        return {t: _q(t, prices[t], source="yfinance-1m") for t in tickers if t in prices}
    return f


def test_latest_quotes_alpaca_hit_makes_no_yfinance_call(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider(quotes={"AAPL": _q("AAPL", 190.0)})); calls = []
    out = router.latest_quotes(["AAPL"], yf_quotes(calls, {}))
    assert calls == [] and out["AAPL"].price == 190.0
    assert router.last_source("AAPL") == "alpaca"


def test_latest_quotes_stale_trade_falls_back_and_keeps_alpaca_bid_ask(enabled, monkeypatch):
    stale = _q("AAPL", None, bid=189.0, ask=191.0)
    _use(monkeypatch, FakeProvider(quotes={"AAPL": stale})); calls = []
    out = router.latest_quotes(["AAPL"], yf_quotes(calls, {"AAPL": 190.4}))
    assert calls == [["AAPL"]]
    q = out["AAPL"]
    assert (q.price, q.source) == (190.4, "yfinance-1m")
    assert (q.bid, q.ask, q.quote_at) == (189.0, 191.0, _T)
    assert router.last_source("AAPL") == "yfinance-fallback"


def test_latest_quotes_fallback_miss_keeps_the_alpaca_quote_only(enabled, monkeypatch):
    stale = _q("AAPL", None, bid=189.0, ask=191.0)
    _use(monkeypatch, FakeProvider(quotes={"AAPL": stale})); calls = []
    out = router.latest_quotes(["AAPL"], yf_quotes(calls, {}))
    assert out["AAPL"] == stale


def test_latest_quotes_ineligible_symbol_is_plain_yfinance(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider()); calls = []
    out = router.latest_quotes(["SAP.DE"], yf_quotes(calls, {"SAP.DE": 50.0}))
    assert calls == [["SAP.DE"]] and out["SAP.DE"].source == "yfinance-1m"
    assert router.last_source("SAP.DE") == "yfinance"


def test_latest_quotes_spot_metal_takes_the_spot_quote(enabled, monkeypatch):
    from swingbot.core.marketdata import spot_metals
    prov = FakeProvider(); _use(monkeypatch, prov); calls = []
    monkeypatch.setattr(spot_metals, "quote_with_reason",
                        lambda t, **k: (spot_metals.SpotQuote(2400.0, _T), None))
    out = router.latest_quotes(["XAUUSD"], yf_quotes(calls, {}))
    assert prov.calls == 0 and calls == []
    assert out["XAUUSD"] == QuoteDetail(symbol="XAUUSD", price=2400.0, trade_at=_T,
                                        bid=None, ask=None, quote_at=None, source="spot")


def test_latest_quotes_runs_on_the_quote_pool(enabled, monkeypatch):
    import threading
    seen = []

    class Probe(FakeProvider):
        def latest_quotes(self, tickers, max_age):
            seen.append(threading.current_thread().name)
            return {}
    _use(monkeypatch, Probe())
    router.latest_quotes(["AAPL"], yf_quotes([], {}))
    assert seen and seen[0].startswith("alpaca-quote")


def test_yf_quote_details_stamps_the_last_bar_in_utc(monkeypatch):
    from swingbot.core.marketdata import data, yf_safe
    idx = pd.DatetimeIndex(["2026-10-16 10:58", "2026-10-16 10:59"]).tz_localize("America/New_York")
    cols = pd.MultiIndex.from_product([["AAPL"], ["Close"]])
    raw = pd.DataFrame([[190.0], [190.5]], index=idx, columns=cols)
    monkeypatch.setattr(yf_safe, "download", lambda *a, **k: raw)
    q = data._yf_quote_details(["AAPL", "MSFT"])
    assert set(q) == {"AAPL"}
    assert q["AAPL"].price == 190.5 and q["AAPL"].source == "yfinance-1m"
    assert q["AAPL"].trade_at == datetime(2026, 10, 16, 14, 59, tzinfo=timezone.utc)


def test_yf_quote_details_busy_lock_is_empty(monkeypatch):
    from swingbot.core.marketdata import data, yf_safe

    def busy(*a, **k):
        raise yf_safe.DownloadBusy("busy")
    monkeypatch.setattr(yf_safe, "download", busy)
    assert data._yf_quote_details(["AAPL"]) == {}


def test_yf_quote_details_reraises_budget_deferred(monkeypatch):
    from swingbot.core.marketdata import data, yf_safe

    def deferred(*a, **k):
        raise yf_safe.BudgetDeferred("tier 5")
    monkeypatch.setattr(yf_safe, "download", deferred)
    with pytest.raises(yf_safe.BudgetDeferred):
        data._yf_quote_details(["AAPL"])


def test_daily_bars_between_is_alpaca_only(enabled, monkeypatch):
    from datetime import date
    prov = FakeProvider(daily={"AAPL"}); _use(monkeypatch, prov)
    out = router.daily_bars_between(["AAPL", "SAP.DE", "XAUUSD"], date(2026, 10, 1), date(2026, 10, 16))
    assert set(out) == {"AAPL"} and out["AAPL"].attrs["source"] == "alpaca"
    assert prov.between == (["AAPL"], date(2026, 10, 1), date(2026, 10, 16))


def test_daily_bars_between_disabled_returns_nothing(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", False); router.reset()
    prov = FakeProvider(daily={"AAPL"}); _use(monkeypatch, prov)
    from datetime import date
    assert router.daily_bars_between(["AAPL"], date(2026, 10, 1), date(2026, 10, 16)) == {}
    assert prov.calls == 0
