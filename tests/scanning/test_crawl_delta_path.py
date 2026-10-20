"""v171 D3: with DAILY_DELTA_FETCH on, the crawl reads the two single-basis
caches, fetches one window per basis in bounded workers, and writes cold
frames back so the next scan is warm."""
import os
from datetime import date

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import daily_delta as dd, data_store, yf_safe
from swingbot.core.marketdata.shared import counters
from swingbot.core.scanning import engine as scan_engine, fetch, runstate
from swingbot.core.scanning.scan_run import ScanProgress
from tests.helpers import make_ohlcv
from tests.marketdata.daily_fakes import Market
from tests.scanning.conftest import _InlineProcessPool

TODAY = date(2026, 10, 16)


@pytest.fixture
def market(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key, value in {"DAILY_DELTA_FETCH": True, "MARKETDATA_LAYER": "off", "ALPACA_ENABLED": True,
                       "ALPACA_ANCHOR_DATE": "2026-01-05", "DELTA_WINDOW_MAX_DAYS": 30,
                       "BATCH_FETCH_CHUNK_SIZE": 100}.items():
        monkeypatch.setattr(config, key, value)
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlineProcessPool)
    monkeypatch.setattr(dd, "_today_ny", lambda: TODAY)
    data_store.clear_normalized_frame_cache()
    m = Market()
    window, full = m.providers(TODAY)
    monkeypatch.setattr(dd, "provider_window", window)
    monkeypatch.setattr(dd, "provider_full", full)
    m.labels = []
    real = fetch._run_bounded

    def bounded(fn, args, timeout, label):
        m.labels.append(label)
        return real(fn, args, timeout, label)
    monkeypatch.setattr(fetch, "_run_bounded", bounded)
    return m


def _forbid(monkeypatch, *names):
    for name in names:
        monkeypatch.setattr(fetch, name, lambda *a, **k: pytest.fail(f"{name} called with the flag on"))


def test_flag_off_keeps_todays_path(monkeypatch, market):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", False)
    _forbid(monkeypatch, "_crawl_delta")
    cached = make_ohlcv([100.0, 101.0, 102.0])
    monkeypatch.setattr(fetch, "_load_cached_daily", lambda t: cached)
    assert scan_engine._crawl_latest_data(["AAPL"])["AAPL"].equals(cached)
    assert market.calls == []


def test_cold_symbols_are_full_fetched_in_workers_and_written_back(monkeypatch, market):
    _forbid(monkeypatch, "_load_cached_daily", "_with_cached_depth")
    frames = scan_engine._crawl_latest_data(["AAPL", "SAP.DE"])
    assert frames["AAPL"].attrs["source"] == "alpaca"
    assert frames["SAP.DE"].attrs["source"] == "yfinance"
    assert frames["AAPL"].index[-1] == pd.Timestamp(TODAY)              # forming bar, in memory
    assert os.path.exists(dd.cache_file("AAPL", dd.BASIS_ALPACA))
    assert os.path.exists(dd.cache_file("SAP.DE", dd.BASIS_YF))
    assert not os.path.exists(dd.cache_file("AAPL", dd.BASIS_YF))      # never crosses
    assert sorted(c[1] for c in market.calls if c[0] == "full") == sorted([dd.BASIS_ALPACA, dd.BASIS_YF])
    assert len(market.labels) == len(market.calls)                      # every provider call bounded
    assert all(label.startswith("Crawl: delta ") for label in market.labels)


def test_the_next_scan_is_warm_one_window_per_basis(monkeypatch, market):
    scan_engine._crawl_latest_data(["AAPL", "MSFT", "SAP.DE"])
    market.calls.clear()
    frames = scan_engine._crawl_latest_data(["AAPL", "MSFT", "SAP.DE"])
    assert sorted(c[1] for c in market.calls) == sorted([dd.BASIS_ALPACA, dd.BASIS_YF])
    assert all(c[0] == "window" for c in market.calls)
    assert all(frames[t].attrs == {} for t in ("AAPL", "MSFT", "SAP.DE"))   # counted as cache


def test_spot_symbols_keep_the_spot_crawl(monkeypatch, market):
    spot = make_ohlcv([2400.0, 2410.0])
    monkeypatch.setattr(fetch, "_crawl_spot", lambda ts, progress=None: {"XAUUSD": spot} if ts else {})
    frames = scan_engine._crawl_latest_data(["AAPL", "XAUUSD"])
    assert frames["XAUUSD"] is spot
    assert all("XAUUSD" not in c[-1] for c in market.calls)


def test_worker_counter_rows_ride_back_and_are_merged(monkeypatch, market):
    row = ("2026-10-16T14:00:00+00:00", "alpaca", "daily", "SCAN", "fetched", 1)
    merged = []
    monkeypatch.setattr(counters, "snapshot_and_clear", lambda: [row])
    monkeypatch.setattr(counters, "merge", lambda rows: merged.extend(rows))
    scan_engine._crawl_latest_data(["AAPL"])
    assert merged and all(r == row for r in merged)


def test_a_failing_delta_chunk_falls_back_to_the_cold_path(monkeypatch, market):
    monkeypatch.setattr(dd, "delta_update", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bug")))
    cold = make_ohlcv([1.0, 2.0, 3.0])
    monkeypatch.setattr(fetch, "_fetch_cold_frames", lambda ts, progress=None: [(t, cold) for t in ts])
    assert scan_engine._crawl_latest_data(["AAPL"])["AAPL"] is cold


# -- fix round 1 ------------------------------------------------------------------------


def _spy_delta(monkeypatch):
    seen = []
    real = dd.delta_update

    def spy(tickers, **kwargs):
        seen.extend(tickers)
        return real(tickers, **kwargs)
    monkeypatch.setattr(dd, "delta_update", spy)
    return seen


def test_an_aliased_ticker_takes_the_legacy_cold_path_and_is_never_cached_by_delta(monkeypatch, market):
    seen = _spy_delta(monkeypatch)
    legacy = make_ohlcv([4000.0, 4010.0, 4020.0])
    cold_asked = []
    monkeypatch.setattr(fetch, "_load_cached_daily", lambda t: None)

    def cold(ts, progress=None):
        cold_asked.extend(ts)
        return [(t, legacy) for t in ts]
    monkeypatch.setattr(fetch, "_fetch_cold_frames", cold)
    frames = scan_engine._crawl_latest_data(["SPX", "AAPL"])
    assert frames["SPX"] is legacy
    assert cold_asked == ["SPX"]
    assert seen == ["AAPL"]                                             # the non-aliased one stays on delta
    assert all("SPX" not in c[-1] for c in market.calls)
    assert not os.path.exists(dd.cache_file("SPX", dd.BASIS_YF))
    assert not os.path.exists(dd.cache_file("SPX", dd.BASIS_ALPACA))


def test_an_aliased_ticker_with_a_fresh_cache_is_served_from_it(monkeypatch, market):
    seen = _spy_delta(monkeypatch)
    cached = make_ohlcv([1.10, 1.11, 1.12])
    monkeypatch.setattr(fetch, "_load_cached_daily", lambda t: cached if t == "EURUSD" else None)
    monkeypatch.setattr(fetch, "_fetch_cold_frames", lambda ts, progress=None: pytest.fail("cold fetch"))
    assert scan_engine._crawl_latest_data(["EURUSD"])["EURUSD"] is cached
    assert seen == [] and market.calls == []


def test_a_failed_window_worker_keeps_the_warm_cached_frame(monkeypatch, market):
    scan_engine._crawl_latest_data(["AAPL"])
    cached = dd.read_daily("AAPL", dd.BASIS_ALPACA)
    monkeypatch.setattr(fetch, "_run_bounded", lambda fn, args, timeout, label: None)   # timed out / raised
    frames = scan_engine._crawl_latest_data(["AAPL"])
    assert frames["AAPL"].index[-1] == cached.index[-1] < pd.Timestamp(TODAY)
    assert len(frames["AAPL"]) == len(cached)


def test_budget_deferred_in_the_worker_is_a_miss(monkeypatch, market):
    def deferred(*a, **k):
        raise yf_safe.BudgetDeferred("short")
    monkeypatch.setattr(dd, "provider_full", deferred)
    monkeypatch.setattr(dd, "provider_window", deferred)
    assert "AAPL" not in scan_engine._crawl_latest_data(["AAPL"])


def test_a_stop_between_chunks_sets_stopped_and_makes_no_calls(monkeypatch, market):
    monkeypatch.setattr(runstate, "is_stop_requested", lambda: True)
    progress = ScanProgress()
    assert dict(scan_engine._crawl_latest_data(["AAPL", "MSFT"], progress)) == {}
    assert progress.stopped is True
    assert market.calls == []


def test_progress_tracks_each_chunk(monkeypatch, market):
    monkeypatch.setattr(config, "BATCH_FETCH_CHUNK_SIZE", 1)
    progress = ScanProgress()
    scan_engine._crawl_latest_data(["AAPL", "MSFT"], progress)
    assert (progress.total, progress.done, progress.current_ticker) == (2, 2, "MSFT")


def test_a_cached_frame_older_than_the_previous_session_is_warned(monkeypatch, market, caplog):
    old = make_ohlcv([1.0, 2.0, 3.0])
    old.index = pd.bdate_range("2026-10-01", periods=3)
    monkeypatch.setattr(dd, "delta_update", lambda tickers, **k: {"AAPL": old})
    with caplog.at_level("WARNING", logger=fetch.log.name):
        assert scan_engine._crawl_latest_data(["AAPL"])["AAPL"] is old
    assert any("AAPL" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records)


def test_a_cached_frame_through_the_previous_session_is_not_warned(monkeypatch, market, caplog):
    recent = make_ohlcv([1.0, 2.0, 3.0])
    recent.index = pd.bdate_range("2026-10-13", periods=3)               # ends 2026-10-15
    monkeypatch.setattr(dd, "delta_update", lambda tickers, **k: {"AAPL": recent})
    with caplog.at_level("WARNING", logger=fetch.log.name):
        scan_engine._crawl_latest_data(["AAPL"])
    assert not [r for r in caplog.records if r.levelname == "WARNING"]
