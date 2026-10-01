"""Provider robustness: bulk-bars deadline, one breaker incident per call,
one in-call retry, one rate-limited WARNING summary."""
import logging
import time

import pytest

from swingbot import config
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaAuthError, AlpacaMiss
from tests.marketdata.test_provider_router import (
    FakeProvider, _df, _size, _syms, _use, yf_daily)


@pytest.fixture
def cfg(monkeypatch):
    for k, v in (("ALPACA_ENABLED", True), ("ALPACA_API_KEY_ID", "k"),
                 ("ALPACA_API_SECRET_KEY", "s"), ("ALPACA_TIMEOUT_SECONDS", 0.3),
                 ("ALPACA_BARS_TIMEOUT_SECONDS", 3.0), ("ALPACA_BREAKER_FAILURES", 2),
                 ("ALPACA_BREAKER_COOLDOWN_SECONDS", 60)):
        monkeypatch.setattr(config, k, v)
    router.reset()
    yield
    router.reset()


class Scripted(FakeProvider):
    """daily_bars: per-batch-first-symbol list of behaviours consumed in order
    (ok, miss, auth or slow)."""
    def __init__(self, script=None, slow=1.0):
        super().__init__()
        self.script, self.slow, self.seen = script or {}, slow, []

    def daily_bars(self, tickers, period):
        self.seen.append(list(tickers))
        steps = self.script.get(tickers[0], [])
        step = steps.pop(0) if steps else "ok"
        if step == "miss":
            raise AlpacaMiss("boom")
        if step == "auth":
            raise AlpacaAuthError("401")
        if step == "slow":
            time.sleep(self.slow)
        return {t: _df() for t in tickers}


def _tries(prov, first):
    return sum(1 for b in prov.seen if b[0] == first)


def test_config_default_and_bounds():
    field = next(f for f in config.FIELDS if f.key == "ALPACA_BARS_TIMEOUT_SECONDS")
    assert field.default == "20" and field.min == 1


def test_daily_bars_use_the_bulk_deadline_not_the_quote_deadline(cfg, monkeypatch):
    prov = Scripted({"AAA": ["slow"]}, slow=0.8)
    _use(monkeypatch, prov)
    out = router.daily_bars(["AAA"], "2y", yf_daily([]))
    assert out["AAA"].attrs["source"] == "alpaca"      # 0.8s > 0.3s quote timeout


def test_quotes_keep_the_short_deadline(cfg, monkeypatch):
    _use(monkeypatch, FakeProvider(prices={"AAPL": 1.0}, sleep=0.8))
    out = router.latest_prices(["AAPL"], lambda ts: {t: 2.0 for t in ts})
    assert out == {"AAPL": 2.0}


def test_intraday_uses_the_bulk_deadline(cfg, monkeypatch):
    prov = FakeProvider()
    prov.intraday_bars = lambda t, iv: (time.sleep(0.8), _df())[1]
    _use(monkeypatch, prov)
    df = router.intraday_bars("AAPL", "1h", lambda t, iv: _df())
    assert df.attrs["source"] == "alpaca"


def test_all_batches_missing_is_one_breaker_incident(cfg, monkeypatch):
    tickers = _syms(8)
    _size(monkeypatch, 2)
    _use(monkeypatch, Scripted({t: ["miss", "miss"] for t in tickers[::2]}))
    router.daily_bars(tickers, "2y", yf_daily([]))
    assert router._breaker.fails == 1 and router.stats()["breaker_open"] is False


def test_consecutive_bad_calls_still_open_the_breaker(cfg, monkeypatch):
    _size(monkeypatch, 2)
    _use(monkeypatch, Scripted({"AAA": ["miss"] * 4}))
    for _ in range(2):
        router.daily_bars(["AAA", "AAB"], "2y", yf_daily([]))
    assert router.stats()["breaker_open"] is True


def test_fully_successful_call_resets_the_failure_count(cfg, monkeypatch):
    _size(monkeypatch, 2)
    _use(monkeypatch, Scripted({}))
    router._active_provider()
    router._breaker.fails = 1
    router.daily_bars(_syms(4), "2y", yf_daily([]))
    assert router._breaker.fails == 0


def test_partial_failure_is_one_failure_not_a_success(cfg, monkeypatch):
    tickers = _syms(4)
    _size(monkeypatch, 2)
    _use(monkeypatch, Scripted({tickers[2]: ["miss", "miss"]}))
    router.daily_bars(tickers, "2y", yf_daily([]))
    assert router._breaker.fails == 1


def test_auth_error_still_latches_at_once_and_is_not_retried(cfg, monkeypatch):
    tickers = _syms(4)
    _size(monkeypatch, 2)
    prov = Scripted({tickers[0]: ["auth"]})
    _use(monkeypatch, prov)
    router.daily_bars(tickers, "2y", yf_daily([]))
    assert router._breaker.auth_latched is True
    assert _tries(prov, tickers[0]) == 1


def test_failed_batch_is_retried_once_then_served_by_alpaca(cfg, monkeypatch):
    tickers = _syms(4)
    _size(monkeypatch, 2)
    prov = Scripted({tickers[2]: ["miss"]})
    _use(monkeypatch, prov)
    calls = []
    out = router.daily_bars(tickers, "2y", yf_daily(calls))
    assert calls == [] and {out[t].attrs["source"] for t in tickers} == {"alpaca"}
    assert _tries(prov, tickers[2]) == 2


def test_batch_failing_twice_falls_back_per_symbol(cfg, monkeypatch):
    tickers = _syms(4)
    _size(monkeypatch, 2)
    prov = Scripted({tickers[2]: ["miss", "miss", "miss"]})
    _use(monkeypatch, prov)
    calls = []
    out = router.daily_bars(tickers, "2y", yf_daily(calls))
    assert calls == [tickers[2:]]
    assert _tries(prov, tickers[2]) == 2               # one retry only
    assert out[tickers[2]].attrs["source"] == "yfinance-fallback"
    assert out[tickers[0]].attrs["source"] == "alpaca"


def test_deadline_expiry_is_not_retried(cfg, monkeypatch):
    monkeypatch.setattr(config, "ALPACA_BARS_TIMEOUT_SECONDS", 0.3)
    prov = Scripted({"AAA": ["slow", "slow"]}, slow=1.0)
    _use(monkeypatch, prov)
    out = router.daily_bars(["AAA"], "2y", yf_daily([]))
    assert len(prov.seen) == 1 and out["AAA"].attrs["source"] == "yfinance-fallback"


def test_summary_warning_names_batches_reason_and_symbols(cfg, monkeypatch, caplog):
    tickers = _syms(4)
    _size(monkeypatch, 2)
    _use(monkeypatch, Scripted({tickers[2]: ["miss", "miss"]}))
    with caplog.at_level(logging.WARNING, logger=router.log.name):
        router.daily_bars(tickers, "2y", yf_daily([]))
    want = "daily_bars: 1/2 batch(es) missed (AlpacaMiss x1); 2 symbol(s) fall back to yfinance"
    assert any(want in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


def test_summary_warning_is_rate_limited_to_once_a_minute(cfg, monkeypatch, caplog):
    monkeypatch.setattr(config, "ALPACA_BREAKER_FAILURES", 20)
    _size(monkeypatch, 2)
    _use(monkeypatch, Scripted({"AAA": ["miss"] * 20}))
    with caplog.at_level(logging.WARNING, logger=router.log.name):
        for _ in range(3):
            router.daily_bars(["AAA", "AAB"], "2y", yf_daily([]))
        assert sum("batch(es) missed" in r.getMessage() for r in caplog.records) == 1
        router._warn_gate.last = time.monotonic() - 61
        router.daily_bars(["AAA", "AAB"], "2y", yf_daily([]))
    assert sum("batch(es) missed" in r.getMessage() for r in caplog.records) == 2


def test_breaker_transition_warning_carries_the_last_reason(cfg, monkeypatch, caplog):
    monkeypatch.setattr(config, "ALPACA_BREAKER_FAILURES", 1)
    _use(monkeypatch, Scripted({"AAA": ["miss"] * 4}))
    with caplog.at_level(logging.WARNING, logger=router.log.name):
        router.daily_bars(["AAA"], "2y", yf_daily([]))
    assert any("breaker OPEN" in r.getMessage() and "AlpacaMiss" in r.getMessage()
               for r in caplog.records)
