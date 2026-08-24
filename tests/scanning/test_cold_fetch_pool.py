"""v47: cold tickers fetch sequentially below the threshold, pooled above it."""
from concurrent.futures import Future

import pytest

from swingbot import config
from swingbot.core.scanning import engine as scan_engine
from tests.helpers import make_ohlcv


def _done_future(result):
    fut = Future()
    fut.set_result(result)
    return fut


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

        def submit(self, fn, ticker):
            return _done_future((ticker, make_ohlcv([1.0, 2.0])))

    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _FakePool)

    pairs = scan_engine._fetch_cold_frames(["A", "B", "C"])

    assert used, "the process pool should have been constructed"
    assert [t for t, _ in pairs] == ["A", "B", "C"]


def test_stuck_ticker_past_the_budget_is_killed_and_treated_as_failed(monkeypatch):
    """A worker that hangs past COLD_FETCH_TIMEOUT_SECONDS (stalled DNS, a
    fork-inherited lock -- yf.download()'s own timeout=10 is not a reliable
    ceiling) must not wedge the whole crawl forever. Production incident
    2026-08-24: session_scan hung 2+ hours, and every tick behind it, because
    one stuck ticker's fetch never returned and nothing bounded the wait."""
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 2)
    monkeypatch.setattr(config, "COLD_FETCH_TIMEOUT_SECONDS", 0.05)
    killed = []
    pool_holder = {}

    class _FakeProcess:
        def kill(self):
            killed.append(True)

    class _FakePool:
        def __init__(self, max_workers=None):
            self._processes = {1: _FakeProcess()}
            self.shutdown_calls = []
            pool_holder["pool"] = self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def submit(self, fn, ticker):
            if ticker == "STUCK":
                return Future()  # never resolved -- simulates a wedged worker
            return _done_future((ticker, make_ohlcv([1.0, 2.0])))

        def shutdown(self, wait=True, cancel_futures=False):
            self.shutdown_calls.append((wait, cancel_futures))

    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _FakePool)

    pairs = scan_engine._fetch_cold_frames(["OK1", "OK2", "STUCK"])

    assert dict(pairs)["STUCK"] is None
    assert dict(pairs)["OK1"] is not None
    assert dict(pairs)["OK2"] is not None
    assert killed, "the stuck worker process must be killed, not left running"
    assert pool_holder["pool"].shutdown_calls == [(False, True)]


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
