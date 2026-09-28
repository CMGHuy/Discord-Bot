"""v109: the crawl fetches spot metals apart from the cache/alias paths and
logs the ratio (or the skip) once per symbol per scan, in the scan process."""
import logging

import pandas as pd
import pytest

from swingbot.core.marketdata import spot_metals as sm
from swingbot.core.scanning import fetch

READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, 4151.70 / 4175.30)


class _InlinePool:
    """Runs _run_bounded's worker inline (same stand-in as
    tests/scanning/test_scan_telemetry_sources.py)."""
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


def _frame(close=4000.0):
    return pd.DataFrame({"Open": [close], "High": [close], "Low": [close],
                         "Close": [close], "Volume": [10.0]},
                        index=pd.DatetimeIndex(["2026-09-25"]))


@pytest.fixture
def crawl(monkeypatch, caplog):
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    caplog.set_level(logging.INFO, logger="swing-bot.scan_engine")
    seen = {"cache": [], "cold": [], "batch": []}

    def cached(t):
        seen["cache"].append(t)
        return _frame(190.0) if t == "AAPL" else None
    monkeypatch.setattr(fetch, "_load_cached_daily", cached)
    monkeypatch.setattr(fetch, "_fetch_cold_frames",
                        lambda ts, progress=None: seen["cold"].extend(ts) or [])
    return seen


def _batch_serves(monkeypatch, seen, frames):
    def batch(tickers, period):
        seen["batch"].append(list(tickers))
        return {t: frames[t] for t in tickers if t in frames}
    monkeypatch.setattr(fetch, "get_daily_data_batch", batch)


def test_spot_symbol_bypasses_cache_and_alias_paths(monkeypatch, crawl, caplog):
    _batch_serves(monkeypatch, crawl, {"XAUUSD": sm.scale_frame(_frame(), READING)})
    results = fetch._crawl_latest_data(["AAPL", "XAUUSD"])
    assert set(results) == {"AAPL", "XAUUSD"}
    assert crawl["cache"] == ["AAPL"]
    assert crawl["cold"] == []
    assert crawl["batch"] == [["XAUUSD"]]
    lines = [r.getMessage() for r in caplog.records]
    assert "XAUUSD: spot ratio 0.99435 (spot 4151.70 / GC=F 4175.30)" in lines
    assert sum("XAUUSD: spot ratio" in m for m in lines) == 1


def test_outage_skips_with_the_reason_and_never_falls_back(monkeypatch, crawl, caplog):
    from swingbot.core.marketdata.providers import router
    _batch_serves(monkeypatch, crawl, {})
    monkeypatch.setattr(router, "spot_miss_reason",
                        lambda t: "spot quote stale (1200s old)")
    results = fetch._crawl_latest_data(["XAUUSD"])
    assert "XAUUSD" not in results
    assert crawl["cold"] == [] and crawl["cache"] == []
    assert ("XAUUSD: skipping new-signal scan -- spot quote unavailable "
            "(spot quote stale (1200s old))") in [r.getMessage() for r in caplog.records]


def test_a_failed_worker_is_a_skip(monkeypatch, crawl, caplog):
    def boom(tickers, period):
        raise RuntimeError("worker died")
    monkeypatch.setattr(fetch, "get_daily_data_batch", boom)
    assert fetch._crawl_latest_data(["XAGUSD"]) == {}
    assert any(r.getMessage().startswith(
        "XAGUSD: skipping new-signal scan -- spot quote unavailable (")
        for r in caplog.records)


def test_progress_counts_spot_symbols(monkeypatch, crawl):
    from swingbot.core.scanning.scan_run import ScanProgress
    _batch_serves(monkeypatch, crawl, {"XAUUSD": sm.scale_frame(_frame(), READING)})
    progress = ScanProgress()
    fetch._crawl_latest_data(["AAPL", "XAUUSD"], progress)
    assert progress.total == 2 and progress.done == 2
