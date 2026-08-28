"""v55: cold tickers fetch via batched, chunked, bounded calls -- no more
per-ticker process-pool threshold. See docs/superpowers/specs/
2026-08-24-v55-scan-fetch-batching-design.md."""
from concurrent.futures import Future

import pytest

from swingbot import config
from swingbot.core.scanning import engine as scan_engine, fetch
from tests.helpers import make_ohlcv


def _done_future(result):
    fut = Future()
    fut.set_result(result)
    return fut


def _raising_future(exc):
    fut = Future()
    fut.set_exception(exc)
    return fut


class _FakePool:
    """Stands in for ProcessPoolExecutor. `submit_fn(fn, *args)` decides
    what Future comes back for each call -- tests plug in whatever
    behaviour (immediate success, immediate raise, or a Future that never
    resolves, simulating a wedged worker) they need."""

    def __init__(self, submit_fn, max_workers=None, mp_context=None):
        self._submit_fn = submit_fn
        self._processes = {1: _FakeProcess()}
        self.shutdown_calls = []

    def __call__(self, max_workers=None, mp_context=None):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *args):
        return self._submit_fn(fn, *args)

    def shutdown(self, wait=True, cancel_futures=False):
        self.shutdown_calls.append((wait, cancel_futures))


class _FakeProcess:
    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True


def _install_fake_pool(monkeypatch, submit_fn):
    pool = _FakePool(submit_fn)
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", pool)
    return pool


# ---------------------------------------------------------------------------
# _run_bounded -- the shared wait-then-kill primitive
# ---------------------------------------------------------------------------

def test_run_bounded_returns_the_result_on_success(monkeypatch):
    _install_fake_pool(monkeypatch, lambda fn, *a: _done_future(fn(*a)))
    assert scan_engine._run_bounded(lambda x: x * 2, (21,), 5, "label") == 42


def test_run_bounded_returns_none_when_fn_raises(monkeypatch, caplog):
    def _boom(*a):
        raise ValueError("nope")
    _install_fake_pool(monkeypatch, lambda fn, *a: _raising_future(ValueError("nope")))
    assert scan_engine._run_bounded(_boom, (), 5, "label") is None
    assert "label" in caplog.text


def test_run_bounded_kills_the_worker_past_the_budget(monkeypatch, caplog):
    pool = _install_fake_pool(monkeypatch, lambda fn, *a: Future())  # never resolves
    result = scan_engine._run_bounded(lambda: None, (), 0.05, "stuck-label")
    assert result is None
    assert pool._processes[1].killed
    # wait=True (v56, was False): the killed worker's manager thread must be
    # joined here, not left running in the background -- an orphaned manager
    # thread alive at the NEXT _run_bounded call's fork() point is what
    # caused every subsequent process-pool call that scan pass to fail
    # instantly with "terminated abruptly" on production 2026-08-24.
    assert pool.shutdown_calls == [(True, True)]
    assert "stuck-label" in caplog.text


# ---------------------------------------------------------------------------
# _fetch_cold_frames -- batched/chunked cold-ticker OHLCV fetch
# ---------------------------------------------------------------------------

def test_empty_cold_list_is_a_no_op(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("must not build a pool for an empty list")
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _boom)
    assert scan_engine._fetch_cold_frames([]) == []


def test_one_chunk_covers_the_whole_cold_list_by_default(monkeypatch):
    calls = []

    def _batch(tickers, period):
        calls.append(list(tickers))
        return {t: make_ohlcv([1.0, 2.0]) for t in tickers}

    monkeypatch.setattr(fetch, "get_daily_data_batch", _batch)
    _install_fake_pool(monkeypatch, lambda fn, *a: _done_future(fn(*a)))

    pairs = scan_engine._fetch_cold_frames(["AAPL", "MSFT", "NVDA"])

    assert len(calls) == 1  # default BATCH_FETCH_CHUNK_SIZE (100) covers all three in one call
    assert [t for t, _ in pairs] == ["AAPL", "MSFT", "NVDA"]
    assert all(df is not None for _, df in pairs)


def test_chunking_splits_a_list_over_the_configured_chunk_size(monkeypatch):
    monkeypatch.setattr(config, "BATCH_FETCH_CHUNK_SIZE", 2)
    calls = []

    def _batch(tickers, period):
        calls.append(list(tickers))
        return {t: make_ohlcv([1.0, 2.0]) for t in tickers}

    monkeypatch.setattr(fetch, "get_daily_data_batch", _batch)
    _install_fake_pool(monkeypatch, lambda fn, *a: _done_future(fn(*a)))

    pairs = scan_engine._fetch_cold_frames(["A", "B", "C", "D", "E"])

    assert calls == [["A", "B"], ["C", "D"], ["E"]]
    assert [t for t, _ in pairs] == ["A", "B", "C", "D", "E"]
    assert all(df is not None for _, df in pairs)


def test_ticker_missing_from_the_batch_falls_back_to_single_ticker_fetch(monkeypatch):
    """A batch call only ever tries a ticker's literal symbol; a ticker
    that needs candidate_symbols() aliasing (or genuinely has no data)
    comes back absent and must fall back to the single-ticker path."""
    monkeypatch.setattr(fetch, "get_daily_data_batch",
                        lambda tickers, period: {"AAPL": make_ohlcv([1.0, 2.0])})
    monkeypatch.setattr(fetch, "get_daily_data",
                        lambda t, period=None: make_ohlcv([9.0, 9.0]))
    _install_fake_pool(monkeypatch, lambda fn, *a: _done_future(fn(*a)))

    pairs = scan_engine._fetch_cold_frames(["AAPL", "ALIASED"])

    by_ticker = dict(pairs)
    assert by_ticker["AAPL"]["Close"].iloc[-1] == 2.0
    assert by_ticker["ALIASED"]["Close"].iloc[-1] == 9.0  # resolved via the fallback


def test_one_failing_chunk_does_not_abort_the_rest(monkeypatch):
    monkeypatch.setattr(config, "BATCH_FETCH_CHUNK_SIZE", 1)

    def _batch(tickers, period):
        if tickers == ["BAD"]:
            raise ValueError("no data returned")
        return {t: make_ohlcv([1.0, 2.0]) for t in tickers}

    monkeypatch.setattr(fetch, "get_daily_data_batch", _batch)
    monkeypatch.setattr(fetch, "get_daily_data",
                        lambda t, period=None: (_ for _ in ()).throw(ValueError("still bad")))

    def _submit(fn, *a):
        try:
            return _done_future(fn(*a))
        except Exception as exc:
            return _raising_future(exc)

    _install_fake_pool(monkeypatch, _submit)

    pairs = scan_engine._fetch_cold_frames(["AAPL", "BAD", "MSFT"])

    by_ticker = dict(pairs)
    assert by_ticker["AAPL"] is not None
    assert by_ticker["MSFT"] is not None
    assert by_ticker["BAD"] is None


def test_stuck_chunk_past_the_budget_is_killed_and_treated_as_failed(monkeypatch):
    """Production incident 2026-08-24: session_scan hung 2+ hours because one
    stuck fetch never returned and nothing bounded the wait. Generalized here
    from one stuck ticker (d251cef) to one stuck batched chunk (v55)."""
    monkeypatch.setattr(config, "COLD_FETCH_TIMEOUT_SECONDS", 0.05)
    pool = _install_fake_pool(monkeypatch, lambda fn, *a: Future())  # never resolves

    pairs = scan_engine._fetch_cold_frames(["AAPL", "MSFT"])

    assert dict(pairs)["AAPL"] is None
    assert dict(pairs)["MSFT"] is None
    assert pool._processes[1].killed
