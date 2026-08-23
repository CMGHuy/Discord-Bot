"""v47: the scan reads market_data/daily/*.csv first and only fetches misses.

At 5-minute ticks over a 6.5h session this is the difference between ~78 full
10-year downloads per ticker per day and ~1.
"""
import pytest

from swingbot.core.scanning import engine as scan_engine
from tests.helpers import make_ohlcv


@pytest.fixture
def no_network(monkeypatch):
    """Any get_daily_data call is recorded; none are allowed to hit yfinance."""
    calls = []

    def _fake(ticker, period=None):
        calls.append(ticker)
        return make_ohlcv([10.0, 11.0, 12.0])

    monkeypatch.setattr(scan_engine, "get_daily_data", _fake)
    return calls


def test_warm_ticker_is_served_from_cache_with_no_fetch(monkeypatch, no_network):
    cached = make_ohlcv([100.0, 101.0, 102.0])
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: cached)

    frames = scan_engine._crawl_latest_data(["AAPL", "MSFT"])

    assert set(frames) == {"AAPL", "MSFT"}
    assert no_network == [], "a warm ticker must cost zero network calls"
    assert frames["AAPL"].equals(cached)


def test_cold_ticker_falls_back_to_a_fetch(monkeypatch, no_network):
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    frames = scan_engine._crawl_latest_data(["AAPL"])

    assert no_network == ["AAPL"]
    assert "AAPL" in frames


def test_mixed_warm_and_cold_fetches_only_the_cold_ones(monkeypatch, no_network):
    cached = make_ohlcv([100.0, 101.0, 102.0])
    monkeypatch.setattr(
        scan_engine, "_load_cached_daily",
        lambda t: cached if t in ("AAPL", "MSFT") else None,
    )

    frames = scan_engine._crawl_latest_data(["AAPL", "MSFT", "NVDA"])

    assert no_network == ["NVDA"]
    assert set(frames) == {"AAPL", "MSFT", "NVDA"}


def test_stop_request_still_ends_the_crawl_early(monkeypatch, no_network):
    """The existing per-ticker stop checkpoint must survive the rewrite."""
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: make_ohlcv([1.0, 2.0]))
    monkeypatch.setattr(scan_engine, "is_stop_requested", lambda: True)

    frames = scan_engine._crawl_latest_data(["AAPL", "MSFT", "NVDA"])

    assert len(frames) == 0


def test_progress_counters_still_advance(monkeypatch, no_network):
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: make_ohlcv([1.0, 2.0]))
    progress = scan_engine.ScanProgress()

    scan_engine._crawl_latest_data(["AAPL", "MSFT"], progress)

    assert progress.total == 2
    assert progress.done == 2
    assert progress.stage == "crawling data"
