"""A cold ticker's shallow live frame gets the stale cache's older history."""
from concurrent.futures import Future

import numpy as np
import pandas as pd

from swingbot.core.scanning import fetch


class _InlinePool:
    def __call__(self, max_workers=None, mp_context=None):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def submit(self, fn, *args):
        fut = Future()
        fut.set_result(fn(*args))
        return fut
    def shutdown(self, wait=True, cancel_futures=False):
        pass


def _full():
    idx = pd.bdate_range("2024-01-01", periods=302)
    close = 100.0 + np.arange(302, dtype="float64")
    df = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                       "Close": close, "Volume": 1000.0}, index=idx)
    df.index.name = "Date"
    return df


def _setup(monkeypatch, cached):
    full = _full()
    live = full.iloc[200:].copy()
    live.attrs["source"] = "alpaca"
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool())
    monkeypatch.setattr(fetch, "get_daily_data_batch", lambda tickers, period: {t: live for t in tickers})
    monkeypatch.setattr(fetch.data_store, "load_normalized",
                        lambda t, tf, *a, **k: cached(full) if cached else None)
    return full, live


def test_cold_frame_is_spliced_with_cached_history(monkeypatch):
    full, live = _setup(monkeypatch, lambda f: f.iloc[:300])
    [(ticker, df)] = fetch._fetch_cold_frames(["AAPL"])
    assert ticker == "AAPL" and len(df) == 302
    assert df.index[0] == full.index[0] and df.index[-1] == live.index[-1]
    assert df.attrs["source"] == "alpaca"


def test_no_cache_leaves_the_live_frame_untouched(monkeypatch):
    _, live = _setup(monkeypatch, None)
    [(_, df)] = fetch._fetch_cold_frames(["AAPL"])
    assert df is live


def test_unreadable_cache_leaves_the_live_frame_untouched(monkeypatch):
    _, live = _setup(monkeypatch, None)
    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(fetch.data_store, "load_normalized", boom)
    [(_, df)] = fetch._fetch_cold_frames(["AAPL"])
    assert df is live


def test_failed_fetch_stays_none(monkeypatch):
    _setup(monkeypatch, lambda f: f.iloc[:300])
    monkeypatch.setattr(fetch, "get_daily_data_batch", lambda tickers, period: {})
    monkeypatch.setattr(fetch, "get_daily_data", lambda t, period=None: (_ for _ in ()).throw(ValueError("x")))
    [(_, df)] = fetch._fetch_cold_frames(["AAPL"])
    assert df is None


def test_daily_frame_for_splices_the_benchmark_too(monkeypatch):
    full, live = _setup(monkeypatch, lambda f: f.iloc[:300])
    monkeypatch.setattr(fetch, "_load_cached_daily", lambda t: None)
    monkeypatch.setattr(fetch, "get_daily_data", lambda t, period=None: live)
    assert len(fetch._daily_frame_for("SPY")) == 302


def test_yfinance_fallback_frame_gets_the_same_cached_depth(monkeypatch):
    """Alpaca down -> the router tags the yfinance frames 'yfinance-fallback';
    the cold scan still splices the cached archive under them."""
    from swingbot import config
    from swingbot.core.marketdata.providers import router
    from swingbot.core.marketdata.providers.alpaca_provider import AlpacaMiss

    class Down:
        def daily_bars(self, tickers, period):
            raise AlpacaMiss("down")

    full, live = _setup(monkeypatch, lambda f: f.iloc[:300])
    for key, val in (("ALPACA_ENABLED", True), ("ALPACA_API_KEY_ID", "k"),
                     ("ALPACA_API_SECRET_KEY", "s")):
        monkeypatch.setattr(config, key, val)
    monkeypatch.setattr(router, "_provider_factory", lambda *a: Down())
    router.reset()
    try:
        monkeypatch.setattr(
            fetch, "get_daily_data_batch",
            lambda tickers, period: router.daily_bars(
                tickers, period, lambda ts, p: {t: live.copy() for t in ts}))
        [(_, df)] = fetch._fetch_cold_frames(["AAPL"])
    finally:
        router.reset()
    assert df.attrs["source"] == "yfinance-fallback"
    assert len(df) == 302 and df.index[0] == full.index[0]
