"""v47 regression guard: a fetched frame must belong to ITS OWN ticker.

This is not a hypothetical. The scan's crawl used to run through a
ThreadPoolExecutor; yfinance 0.2.66 builds download() on a shared, non-reentrant
module global (_DFS), and two real watchlist tickers scanned seconds apart in
the same concurrent batch were once logged as open paper trades with
byte-identical entry/stop/target/confidence values -- one ticker's price data
had been attributed to the other. The crawl was made sequential in response.

v47 restores concurrency using PROCESSES instead of threads, so the shared
global is not shared. This test asserts the routing that makes that claim true:
each ticker's frame carries a price signature derived from its own symbol, so a
swap is detectable without any network and without trusting Yahoo's data.
"""
from concurrent.futures import Future

import pytest

from swingbot import config
from swingbot.core.scanning import engine as scan_engine
from tests.helpers import make_ohlcv


def _signature_price(ticker: str) -> float:
    """A per-ticker price no other ticker in the batch can produce."""
    return 100.0 + sum(ord(c) for c in ticker)


def _identifiable_frame(ticker: str, period=None):
    base = _signature_price(ticker)
    return make_ohlcv([base, base + 1.0, base + 2.0])


@pytest.fixture
def identifiable_fetch(monkeypatch):
    monkeypatch.setattr(scan_engine, "get_daily_data", _identifiable_frame)


class _InlinePool:
    """Stands in for ProcessPoolExecutor: no subprocess, no network, but the
    real _fetch_one_ticker and the real result-merging still run.

    A REAL pool cannot be used here. Workers are separate interpreters, so the
    monkeypatched get_daily_data does not exist in them and every ticker in the
    batch would hit the live network.
    """

    def __init__(self, max_workers=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, ticker):
        # _fetch_cold_frames keys each result off the Future object this
        # call returns (via a {future: ticker} dict), never off completion
        # order or position -- so misattribution is structurally impossible
        # regardless of what order these resolve in.
        fut = Future()
        fut.set_result(fn(ticker))
        return fut


BATCH = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOG", "META", "NFLX",
         "AMD", "INTC", "ORCL", "CRM"]


def test_sequential_path_never_mixes_tickers(monkeypatch, identifiable_fetch):
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", len(BATCH) + 1)

    pairs = scan_engine._fetch_cold_frames(list(BATCH))

    assert [t for t, _ in pairs] == BATCH
    for ticker, df in pairs:
        assert df is not None
        assert df["Close"].iloc[0] == _signature_price(ticker), (
            f"{ticker} received another ticker's data"
        )


def test_pooled_path_never_mixes_tickers(monkeypatch, identifiable_fetch):
    """Above the threshold the pool is used."""
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 2)
    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _InlinePool)

    pairs = scan_engine._fetch_cold_frames(list(BATCH))

    assert [t for t, _ in pairs] == BATCH
    for ticker, df in pairs:
        assert df is not None
        assert df["Close"].iloc[0] == _signature_price(ticker), (
            f"{ticker} received another ticker's data"
        )


def test_frames_reach_the_crawl_result_under_their_own_key(monkeypatch, identifiable_fetch):
    """End-to-end through _crawl_latest_data: nothing between the fetch and
    the LRUFrames result may re-key a frame."""
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 2)
    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    frames = scan_engine._crawl_latest_data(list(BATCH))

    for ticker in BATCH:
        assert frames[ticker]["Close"].iloc[0] == _signature_price(ticker)


def test_fetch_one_ticker_returns_its_own_symbol(identifiable_fetch):
    """The invariant the pooled path depends on: the worker's return value
    carries the ticker, so results are never matched up by position alone."""
    ticker, df = scan_engine._fetch_one_ticker("NVDA")
    assert ticker == "NVDA"
    assert df["Close"].iloc[0] == _signature_price("NVDA")
