"""v47/v55 regression guard: a fetched frame must belong to ITS OWN ticker.

This is not a hypothetical. The scan's crawl used to run through a
ThreadPoolExecutor; yfinance 0.2.66 builds download() on a shared, non-reentrant
module global (_DFS), and two real watchlist tickers scanned seconds apart in
the same concurrent batch were once logged as open paper trades with
byte-identical entry/stop/target/confidence values -- one ticker's price data
had been attributed to the other. The crawl was made sequential in response,
then (v47) restored concurrency using PROCESSES instead of threads.

v55 changed the mechanism again: cold tickers now fetch through ONE batched
get_daily_data_batch() call per chunk (keyed by ticker, via yf.download's own
group_by="ticker" multi-index) instead of one call per ticker. This test
asserts the routing that makes "no cross-ticker mixing" still true under
batching: each ticker's frame carries a price signature derived from its own
symbol, so a swap is detectable without any network and without trusting
Yahoo's data.
"""
import pytest

from swingbot import config
from swingbot.core.scanning import engine as scan_engine
from tests.helpers import make_ohlcv


def _signature_price(ticker: str) -> float:
    """A per-ticker price no other ticker in the batch can produce."""
    return 100.0 + sum(ord(c) for c in ticker)


def _identifiable_batch(tickers, period=None):
    return {
        t: make_ohlcv([_signature_price(t), _signature_price(t) + 1.0, _signature_price(t) + 2.0])
        for t in tickers
    }


def _identifiable_single(ticker, period=None):
    base = _signature_price(ticker)
    return make_ohlcv([base, base + 1.0, base + 2.0])


@pytest.fixture
def identifiable_fetch(monkeypatch):
    monkeypatch.setattr(scan_engine, "get_daily_data_batch", _identifiable_batch)
    monkeypatch.setattr(scan_engine, "get_daily_data", _identifiable_single)


class _InlinePool:
    """Stands in for ProcessPoolExecutor: no subprocess, no network, but the
    real _fetch_cold_frames/_run_bounded routing still runs.

    A REAL pool cannot be used here. Workers are separate interpreters, so the
    monkeypatched get_daily_data_batch does not exist in them and every
    ticker in the batch would hit the live network.
    """

    def __init__(self, max_workers=None, mp_context=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *args):
        from concurrent.futures import Future
        fut = Future()
        try:
            fut.set_result(fn(*args))
        except Exception as exc:
            fut.set_exception(exc)
        return fut


BATCH = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOG", "META", "NFLX",
         "AMD", "INTC", "ORCL", "CRM"]


def test_batched_fetch_never_mixes_tickers(monkeypatch, identifiable_fetch):
    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _InlinePool)

    pairs = scan_engine._fetch_cold_frames(list(BATCH))

    assert [t for t, _ in pairs] == BATCH
    for ticker, df in pairs:
        assert df is not None
        assert df["Close"].iloc[0] == _signature_price(ticker), (
            f"{ticker} received another ticker's data"
        )


def test_chunked_batches_never_mix_tickers(monkeypatch, identifiable_fetch):
    """Same guarantee split across multiple chunks -- each chunk's own
    get_daily_data_batch() call must key its results correctly, and the
    reassembly across chunks must not shuffle anything either."""
    monkeypatch.setattr(config, "BATCH_FETCH_CHUNK_SIZE", 5)
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
    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    frames = scan_engine._crawl_latest_data(list(BATCH))

    for ticker in BATCH:
        assert frames[ticker]["Close"].iloc[0] == _signature_price(ticker)


def test_fetch_one_ticker_returns_its_own_symbol(identifiable_fetch):
    """The invariant the alias-resolution fallback path depends on: the
    worker's return value carries the ticker, so results are never matched
    up by position alone."""
    ticker, df = scan_engine._fetch_one_ticker("NVDA")
    assert ticker == "NVDA"
    assert df["Close"].iloc[0] == _signature_price("NVDA")


def test_live_price_batch_never_mixes_tickers(monkeypatch):
    def _identifiable_price_batch(tickers):
        return {t: _signature_price(t) for t in tickers}

    monkeypatch.setattr(scan_engine, "get_current_price_batch", _identifiable_price_batch)
    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _InlinePool)

    prices = scan_engine._fetch_live_prices(list(BATCH))

    for ticker in BATCH:
        assert prices[ticker] == _signature_price(ticker), (
            f"{ticker} received another ticker's live price"
        )
