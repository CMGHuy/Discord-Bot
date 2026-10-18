"""v171 D6: in `on` mode every Alpaca and yfinance call takes a token from the
one shared budget at the asker's tier; off/count keep the per-process bucket."""
import threading
import time

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import yf_safe
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaMiss
from swingbot.core.marketdata.shared import budget
from swingbot.core.marketdata.shared.kinds import PROVIDER_ALPACA, PROVIDER_YF, Asker


def _df():
    return pd.DataFrame({"Close": [1.0]}, index=pd.DatetimeIndex(["2026-10-15"]))


class FakeProvider:
    def __init__(self, prices=None, exc=None):
        self.prices, self.exc, self.calls, self.askers = prices or {}, exc, 0, []

    def latest_prices(self, tickers, max_age):
        self.calls += 1
        self.askers.append((router.current_asker(), threading.current_thread().name))
        if self.exc:
            raise self.exc
        return {t: p for t, p in self.prices.items() if t in tickers}

    def daily_bars(self, tickers, period):
        self.calls += 1
        return {t: _df() for t in tickers}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", True)
    monkeypatch.setattr(config, "ALPACA_API_KEY_ID", "k")
    monkeypatch.setattr(config, "ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setattr(config, "ALPACA_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(config, "ALPACA_BARS_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(config, "ALPACA_BREAKER_FAILURES", 1)
    monkeypatch.setattr(config, "ALPACA_BREAKER_COOLDOWN_SECONDS", 60)
    router.reset()
    yield
    router.reset()


@pytest.fixture
def shared(monkeypatch):
    """Records every budget call; tokens and breaker answers are set per test."""
    rec = {"take": [], "allows": [], "record": [], "grant": True, "closed": True}

    def take(provider, asker):
        rec["take"].append((provider, asker))
        return rec["grant"]

    def allows(provider):
        rec["allows"].append(provider)
        return rec["closed"]

    monkeypatch.setattr(budget, "take", take)
    monkeypatch.setattr(budget, "breaker_allows", allows)
    monkeypatch.setattr(budget, "breaker_record", lambda p, ok: rec["record"].append((p, ok)))
    return rec


def _use(monkeypatch, prov):
    monkeypatch.setattr(router, "_provider_factory", lambda *a: prov)


def _mode(monkeypatch, mode):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", mode)
    router.reset()


def test_default_asker_is_scan_and_scopes_nest_and_reset():
    assert router.current_asker() is Asker.SCAN
    with router.asker_scope(Asker.STOP_MONITOR):
        assert router.current_asker() is Asker.STOP_MONITOR
        with router.asker_scope(Asker.ADMIN_PAGE):
            assert router.current_asker() is Asker.ADMIN_PAGE
        assert router.current_asker() is Asker.STOP_MONITOR
    assert router.current_asker() is Asker.SCAN


@pytest.mark.parametrize("mode", ["off", "count"])
def test_off_and_count_use_the_local_bucket_and_never_the_budget(enabled, shared, monkeypatch, mode):
    _mode(monkeypatch, mode)
    prov = FakeProvider(prices={"AAPL": 190.0}); _use(monkeypatch, prov)
    router._bucket = router._Bucket(per_minute=1)
    assert router.latest_prices(["AAPL"], lambda ts: {}) == {"AAPL": 190.0}
    assert router.latest_prices(["AAPL"], lambda ts: {"AAPL": 189.0}) == {"AAPL": 189.0}
    assert prov.calls == 1                       # second call had no local token
    monkeypatch.setattr(yf_safe.yf, "download", lambda *a, **k: _df())
    assert not yf_safe.download("AAPL", period="1d").empty
    assert shared["take"] == shared["allows"] == shared["record"] == []


def test_on_takes_one_shared_token_at_the_current_asker(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    prov = FakeProvider(prices={"AAPL": 190.0}); _use(monkeypatch, prov)
    router._bucket.tokens = 0.0                  # the local bucket is not consulted
    with router.asker_scope(Asker.STOP_MONITOR):
        assert router.latest_prices(["AAPL"], lambda ts: {}) == {"AAPL": 190.0}
    assert shared["take"] == [(PROVIDER_ALPACA, Asker.STOP_MONITOR)]
    assert shared["record"] == [(PROVIDER_ALPACA, True)]


def test_on_asker_reaches_the_router_pool_thread(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    prov = FakeProvider(prices={"AAPL": 190.0}); _use(monkeypatch, prov)
    with router.asker_scope(Asker.REQUOTE):
        router.latest_prices(["AAPL"], lambda ts: {})
    asker, thread = prov.askers[0]
    assert asker is Asker.REQUOTE and thread.startswith("alpaca-quote")


def test_on_denied_token_falls_back_to_yfinance(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    shared["grant"] = False
    prov = FakeProvider(prices={"AAPL": 190.0}); _use(monkeypatch, prov)
    out = router.latest_prices(["AAPL"], lambda ts: {"AAPL": 189.5})
    assert prov.calls == 0 and out == {"AAPL": 189.5}
    assert router.last_source("AAPL") == "yfinance-fallback"


def test_on_round_takes_one_token_per_batch(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    monkeypatch.setattr(router, "symbols_per_request", lambda period: 1)
    _use(monkeypatch, FakeProvider())
    with router.asker_scope(Asker.BACKGROUND):
        out = router.daily_bars(["AAPL", "MSFT", "NVDA"], "10y", lambda ts, p: {})
    assert set(out) == {"AAPL", "MSFT", "NVDA"}
    assert shared["take"] == [(PROVIDER_ALPACA, Asker.BACKGROUND)] * 3


def test_on_open_shared_breaker_sends_everything_to_plain_yfinance(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    shared["closed"] = False
    prov = FakeProvider(prices={"AAPL": 190.0}); _use(monkeypatch, prov)
    out = router.latest_prices(["AAPL"], lambda ts: {"AAPL": 189.0})
    assert prov.calls == 0 and out == {"AAPL": 189.0}
    assert router.last_source("AAPL") == "yfinance"
    assert shared["take"] == []


def test_on_failed_call_mirrors_a_failure_verdict(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    _use(monkeypatch, FakeProvider(exc=AlpacaMiss("boom")))
    router.latest_prices(["AAPL"], lambda ts: {})
    assert shared["record"] == [(PROVIDER_ALPACA, False)]


def test_on_shared_breaker_read_is_memoised_and_reread_after_a_verdict(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    _use(monkeypatch, FakeProvider(prices={"AAPL": 190.0}))
    router._active_provider(); router._active_provider()
    assert len(shared["allows"]) == 1
    router.latest_prices(["AAPL"], lambda ts: {})     # records a verdict
    router._active_provider()
    assert len(shared["allows"]) == 2
    router.reset(); router._active_provider()           # reset clears the memo
    assert len(shared["allows"]) == 3


def test_yf_download_on_takes_a_yf_token_at_the_current_asker(shared, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(yf_safe.yf, "download", lambda *a, **k: _df())
    with router.asker_scope(Asker.BACKGROUND):
        yf_safe.download("AAPL", period="1d")
    assert shared["take"] == [(PROVIDER_YF, Asker.BACKGROUND)]


@pytest.mark.parametrize("asker", [Asker.BACKGROUND, Asker.ADMIN_PAGE, Asker.ADMIN_DASHBOARD,
                                   Asker.ADMIN_FRESH])
def test_yf_download_denied_tier_4_5_is_deferred_without_downloading(shared, monkeypatch, asker):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    shared["grant"] = False
    calls = []
    monkeypatch.setattr(yf_safe.yf, "download", lambda *a, **k: calls.append(a) or _df())
    with router.asker_scope(asker), pytest.raises(yf_safe.BudgetDeferred):
        yf_safe.download("AAPL", period="1d")
    assert calls == []
    assert yf_safe.BudgetDeferred is budget.BudgetDeferred


@pytest.mark.parametrize("asker", [Asker.STOP_MONITOR, Asker.REQUOTE, Asker.SCAN])
def test_yf_download_tiers_1_to_3_are_never_denied(shared, monkeypatch, asker):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    shared["grant"] = False
    monkeypatch.setattr(yf_safe.yf, "download", lambda *a, **k: _df())
    with router.asker_scope(asker):
        assert not yf_safe.download("AAPL", period="1d").empty
