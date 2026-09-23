import numpy as np
import pandas as pd
import pytest

from swingbot.core.marketdata import data as data_mod
from swingbot.core.marketdata.data import FETCH_RETRY_ATTEMPTS
from tests.conftest import make_ohlcv


def _batch_frame(prices: dict) -> pd.DataFrame:
    """Builds a yf.download(..., group_by="ticker") -shaped multi-index
    frame: level 0 = ticker, level 1 = OHLCV field -- verified against a
    real yfinance 0.2.66 batch response during the v55 investigation."""
    per_ticker = {ticker: make_ohlcv(closes) for ticker, closes in prices.items()}
    return pd.concat(per_ticker, axis=1)


def test_concurrent_price_and_daily_fetches_never_overlap_inside_yfinance(monkeypatch):
    """yfinance 0.2.66's download() shares module globals across calls, so
    two in-process downloads at once corrupt each other. Production logged
    "dictionary changed size during iteration" and a chart built from another
    ticker's columns. Every in-process call must be serialised."""
    import threading
    import time

    state = {"active": 0, "max": 0}
    guard = threading.Lock()

    def _fake(*a, **kw):
        with guard:
            state["active"] += 1
            state["max"] = max(state["max"], state["active"])
        time.sleep(0.05)
        with guard:
            state["active"] -= 1
        return make_ohlcv([10.0, 11.0])

    monkeypatch.setattr(data_mod.yf, "download", _fake)
    workers = [threading.Thread(target=data_mod.get_daily_data, args=(f"T{i}",)) for i in range(4)]
    workers += [threading.Thread(target=data_mod.get_current_price_batch, args=([f"P{i}"],),
                                 kwargs={"allow_stale": False}) for i in range(4)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert state["max"] == 1


def test_get_daily_data_retries_a_transient_failure_before_falling_back(monkeypatch):
    """A transient failure on the first candidate must be retried before
    ticker_utils.candidate_symbols() moves on to an alias -- otherwise a
    single rate-limit blip on a ticker with no real alias (the common case)
    raises ValueError immediately instead of recovering."""
    monkeypatch.setattr("swingbot.core.infra.retry.time.sleep", lambda s: None)
    good = make_ohlcv([10.0, 11.0])
    calls = []
    attempts = {"n": 0}

    def _flaky(symbol, **kw):
        calls.append(symbol)
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("rate limited")
        return good
    monkeypatch.setattr(data_mod.yf, "download", _flaky)

    df = data_mod.get_daily_data("CRM")

    assert calls == ["CRM", "CRM"]   # same candidate retried, no alias fallback needed
    assert len(df) == len(good)


def test_get_daily_data_gives_up_after_retries_then_tries_next_candidate(monkeypatch):
    monkeypatch.setattr("swingbot.core.infra.retry.time.sleep", lambda s: None)
    good = make_ohlcv([500.0])
    calls = []

    def _fake(symbol, **kw):
        calls.append(symbol)
        if symbol == "SPX":
            raise ConnectionError("still down")
        return good
    monkeypatch.setattr(data_mod.yf, "download", _fake)

    df = data_mod.get_daily_data("SPX")

    assert calls == ["SPX"] * FETCH_RETRY_ATTEMPTS + ["^GSPC"]
    assert len(df) == len(good)


def test_get_daily_data_batch_keys_each_ticker_to_its_own_slice(monkeypatch):
    frame = _batch_frame({"AAA": [10.0, 11.0], "BBB": [200.0, 201.0]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)

    out = data_mod.get_daily_data_batch(["AAA", "BBB"])

    assert set(out) == {"AAA", "BBB"}
    assert out["AAA"]["Close"].iloc[-1] == 11.0
    assert out["BBB"]["Close"].iloc[-1] == 201.0


def test_get_daily_data_batch_normalises_and_deduplicates_inputs(monkeypatch):
    requested = []

    def download(symbols, *_args, **_kwargs):
        requested.append(symbols)
        return _batch_frame({"AAA": [10.0], "BBB": [20.0]})

    monkeypatch.setattr(data_mod.yf, "download", download)

    data_mod.get_daily_data_batch(["aaa", "AAA", " bbb ", None])
    assert requested == ["AAA BBB"]


def test_get_daily_data_batch_omits_a_ticker_with_no_data(monkeypatch):
    """A batch response only ever contains columns for the tickers Yahoo
    actually recognized -- a delisted/bad symbol is simply absent, not a
    column of NaNs, but the same "absent means unavailable" contract must
    hold for a slice that IS present but comes back all-NaN too."""
    frame = _batch_frame({"AAA": [10.0, 11.0]})
    nan_cols = pd.concat(
        {"BAD": pd.DataFrame({"Open": [np.nan], "High": [np.nan], "Low": [np.nan],
                              "Close": [np.nan], "Volume": [np.nan]},
                             index=frame.index[-1:])},
        axis=1)
    frame = pd.concat([frame, nan_cols], axis=1)
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)

    out = data_mod.get_daily_data_batch(["AAA", "BAD", "MISSING"])

    assert set(out) == {"AAA"}


def test_get_daily_data_batch_empty_response_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: pd.DataFrame())
    assert data_mod.get_daily_data_batch(["AAA", "BBB"]) == {}


def test_get_daily_data_batch_raising_download_returns_empty_dict(monkeypatch):
    monkeypatch.setattr("swingbot.core.infra.retry.time.sleep", lambda s: None)
    calls = []

    def _boom(*a, **kw):
        calls.append(1)
        raise ConnectionError("no route to host")
    monkeypatch.setattr(data_mod.yf, "download", _boom)
    assert data_mod.get_daily_data_batch(["AAA"]) == {}
    assert len(calls) == FETCH_RETRY_ATTEMPTS  # retried, not a single shot


def test_get_daily_data_batch_retries_a_transient_failure_then_succeeds(monkeypatch):
    """A rate-limited/transient yfinance failure on the first attempt must
    not cost this ticker's whole 5-minute scan cycle -- see the 2026-09
    production investigation: YFPricesMissingError hit real, actively-traded
    tickers (CRM, SOFI, SNOW, ...) and even the benchmark indices, and with
    no retry each hit simply dropped that ticker for the cycle."""
    monkeypatch.setattr("swingbot.core.infra.retry.time.sleep", lambda s: None)
    frame = _batch_frame({"AAA": [10.0, 11.0]})
    attempts = {"n": 0}

    def _flaky(*a, **kw):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("rate limited")
        return frame
    monkeypatch.setattr(data_mod.yf, "download", _flaky)

    out = data_mod.get_daily_data_batch(["AAA"])

    assert set(out) == {"AAA"}
    assert attempts["n"] == 2


def test_get_daily_data_batch_empty_ticker_list_never_calls_download(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("must not call yf.download for an empty ticker list")
    monkeypatch.setattr(data_mod.yf, "download", _boom)
    assert data_mod.get_daily_data_batch([]) == {}


def test_get_current_price_batch_uses_last_close_per_ticker(monkeypatch):
    frame = _batch_frame({"AAA": [10.0, 11.0, 12.5], "BBB": [200.0, 199.0]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)

    out = data_mod.get_current_price_batch(["AAA", "BBB"])

    assert out == {"AAA": 12.5, "BBB": 199.0}


def test_get_current_price_batch_normalises_and_deduplicates_inputs(monkeypatch):
    monkeypatch.setattr(data_mod, "_last_good_batch_price", {})
    requested = []

    def download(symbols, *_args, **_kwargs):
        requested.append(symbols)
        return _batch_frame({"AAA": [10.0], "BBB": [20.0]})

    monkeypatch.setattr(data_mod.yf, "download", download)

    assert data_mod.get_current_price_batch(["aaa", "AAA", " bbb ", "", None]) == {
        "AAA": 10.0, "BBB": 20.0,
    }
    assert requested == ["AAA BBB"]


def test_get_current_price_batch_omits_a_ticker_with_no_price(monkeypatch):
    frame = _batch_frame({"AAA": [10.0, 11.0]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)

    out = data_mod.get_current_price_batch(["AAA", "MISSING"])

    assert set(out) == {"AAA"}


def test_get_current_price_batch_falls_back_to_the_last_good_price_on_failure(monkeypatch):
    """2026-09-14: a transient batch failure used to blank EVERY ticker's
    price for the tick (return {}), reported as the market/watchlist tape
    persistently showing "no price" for tickers that plainly have one.
    Deliberately NOT fixed with with_retry (reverted the same day --
    test_api_v1_watchlist.py's under-1s contract on this exact call), so
    this pins the actual fix: a failed batch call falls back to each
    ticker's own last known-good price from a PRIOR successful call,
    instead of losing it."""
    frame = _batch_frame({"ZZFB1": [42.0, 43.5]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)
    first = data_mod.get_current_price_batch(["ZZFB1"])
    assert first == {"ZZFB1": 43.5}

    calls = {"n": 0}

    def failing(*a, **kw):
        calls["n"] += 1
        raise RuntimeError("Yahoo throttled")
    monkeypatch.setattr(data_mod.yf, "download", failing)
    # Move past the display-cache TTL but remain inside the longer
    # last-known-good fallback window, so this exercises failure recovery.
    future = data_mod.time.monotonic() + data_mod._BATCH_PRICE_CACHE_TTL_SECONDS + 1
    monkeypatch.setattr(data_mod.time, "monotonic", lambda: future)

    out = data_mod.get_current_price_batch(["ZZFB1"])

    assert out == {"ZZFB1": 43.5}
    # No retry: this path must not add blocking latency to a failure --
    # exactly one call, not FETCH_RETRY_ATTEMPTS-worth.
    assert calls["n"] == 1


def test_get_current_price_batch_fallback_expires(monkeypatch):
    """The fallback is a bridge over a momentary gap, not a permanent
    stand-in for a ticker Yahoo has stopped answering for."""
    frame = _batch_frame({"ZZFB2": [10.0]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)
    assert data_mod.get_current_price_batch(["ZZFB2"]) == {"ZZFB2": 10.0}

    # Jump the fallback clock past its TTL, as if a long time had passed.
    future = data_mod.time.monotonic() + data_mod._LAST_GOOD_BATCH_PRICE_TTL_SECONDS + 1
    monkeypatch.setattr(data_mod.time, "monotonic", lambda: future)
    monkeypatch.setattr(data_mod.yf, "download",
                         lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("still down")))

    assert data_mod.get_current_price_batch(["ZZFB2"]) == {}


def test_get_current_price_batch_fresh_only_never_uses_last_good_on_failure(monkeypatch):
    frame = _batch_frame({"FRESH1": [10.0]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)
    assert data_mod.get_current_price_batch(["FRESH1"]) == {"FRESH1": 10.0}
    monkeypatch.setattr(data_mod.yf, "download",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("down")))
    assert data_mod.get_current_price_batch(["FRESH1"], allow_stale=False) == {}


def test_get_current_price_batch_reuses_a_short_lived_display_quote(monkeypatch):
    calls = {"n": 0}

    def download(*_args, **_kwargs):
        calls["n"] += 1
        return _batch_frame({"DISPLAY1": [25.0]})

    monkeypatch.setattr(data_mod.yf, "download", download)
    assert data_mod.get_current_price_batch(["DISPLAY1"]) == {"DISPLAY1": 25.0}
    assert data_mod.get_current_price_batch(["DISPLAY1"]) == {"DISPLAY1": 25.0}
    assert calls["n"] == 1


def test_peek_cached_batch_price_returns_nothing_before_anything_fetched():
    assert data_mod.peek_cached_batch_price(["ZZPEEK1"]) == {}


def test_peek_cached_batch_price_returns_the_cached_value_without_fetching(monkeypatch):
    frame = _batch_frame({"ZZPEEK2": [12.0]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)
    data_mod.get_current_price_batch(["ZZPEEK2"])  # populates the cache

    def boom(*a, **kw):
        raise AssertionError("peek must never fetch")
    monkeypatch.setattr(data_mod.yf, "download", boom)

    assert data_mod.peek_cached_batch_price(["ZZPEEK2"]) == {"ZZPEEK2": 12.0}


def test_warm_batch_price_cache_background_populates_the_cache(monkeypatch):
    frame = _batch_frame({"ZZWARM1": [7.0]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)

    thread = data_mod.warm_batch_price_cache_background(["ZZWARM1"])
    thread.join(timeout=5)

    assert data_mod.peek_cached_batch_price(["ZZWARM1"]) == {"ZZWARM1": 7.0}


def test_warm_batch_price_cache_background_survives_a_failing_batch(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("Yahoo throttled")
    monkeypatch.setattr(data_mod.yf, "download", boom)

    thread = data_mod.warm_batch_price_cache_background(["ZZWARM2"])
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert data_mod.peek_cached_batch_price(["ZZWARM2"]) == {}


def test_prefetch_prices_batches_once_and_warms_the_single_price_cache(monkeypatch):
    monkeypatch.setattr(data_mod, "_price_cache", {})
    calls = []

    monkeypatch.setattr(
        data_mod, "get_current_price_batch",
        lambda tickers: calls.append(tickers) or {"AAPL": 101.5, "MSFT": 202.5},
    )

    data_mod.prefetch_prices(["aapl", "MSFT", "AAPL"])

    assert calls == [["AAPL", "MSFT"]]
    assert data_mod.get_current_price("AAPL") == 101.5
    assert data_mod.get_current_price("MSFT") == 202.5


def test_fresh_only_single_price_uses_a_fresh_display_cache(monkeypatch):
    monkeypatch.setattr(
        data_mod, "_price_cache", {"FRESH-ONLY": (99.0, data_mod.time.monotonic(), False)}
    )

    class Ticker:
        def __init__(self, _symbol):
            pass

        def history(self, **_kwargs):
            raise RuntimeError("provider unavailable")

        @property
        def fast_info(self):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(data_mod.yf, "Ticker", Ticker)
    assert data_mod.get_current_price("FRESH-ONLY", allow_stale=False) == 99.0
