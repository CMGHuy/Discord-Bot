"""v47: cold tickers fetch sequentially below the threshold, pooled above it."""
import pytest

from swingbot import config
from swingbot.core.scanning import engine as scan_engine
from tests.helpers import make_ohlcv


def test_resolve_workers_auto_is_at_least_one(monkeypatch):
    monkeypatch.setattr(config, "FETCH_WORKERS", 0)
    assert scan_engine._resolve_workers() >= 1


def test_resolve_workers_honours_an_explicit_value(monkeypatch):
    monkeypatch.setattr(config, "FETCH_WORKERS", 3)
    assert scan_engine._resolve_workers() == 3


def test_below_threshold_never_builds_a_process_pool(monkeypatch):
    """The common case (a ticker or two the refresh loop hasn't caught up on)
    must take today's exact sequential path -- zero new risk surface."""
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 10)
    monkeypatch.setattr(scan_engine, "get_daily_data",
                        lambda t, period=None: make_ohlcv([1.0, 2.0, 3.0]))

    def _boom(*a, **kw):
        raise AssertionError("process pool must not be built below the threshold")

    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _boom)

    pairs = scan_engine._fetch_cold_frames(["AAPL", "MSFT"])

    assert [t for t, _ in pairs] == ["AAPL", "MSFT"]
    assert all(df is not None for _, df in pairs)


def test_above_threshold_uses_the_process_pool(monkeypatch):
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 2)
    used = []

    class _FakePool:
        def __init__(self, max_workers=None):
            used.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def map(self, fn, items):
            return [(t, make_ohlcv([1.0, 2.0])) for t in items]

    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _FakePool)

    pairs = scan_engine._fetch_cold_frames(["A", "B", "C"])

    assert used, "the process pool should have been constructed"
    assert [t for t, _ in pairs] == ["A", "B", "C"]


def test_one_failing_ticker_does_not_abort_the_batch(monkeypatch):
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 10)

    def _flaky(ticker, period=None):
        if ticker == "BAD":
            raise ValueError("no data returned")
        return make_ohlcv([1.0, 2.0])

    monkeypatch.setattr(scan_engine, "get_daily_data", _flaky)

    pairs = scan_engine._fetch_cold_frames(["AAPL", "BAD", "MSFT"])

    assert [t for t, _ in pairs] == ["AAPL", "BAD", "MSFT"]
    assert dict(pairs)["BAD"] is None
    assert dict(pairs)["AAPL"] is not None


def test_empty_cold_list_is_a_no_op(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("must not build a pool for an empty list")

    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _boom)
    assert scan_engine._fetch_cold_frames([]) == []
