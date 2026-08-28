"""v47: SPY and the sector ETFs come from the cache too.

They are ~12 further sequential fetches per scan on top of the watchlist crawl.
"""
import pytest

from swingbot.core.scanning import engine as scan_engine, fetch
from tests.helpers import make_ohlcv
from tests.scanning.conftest import _InlineProcessPool


@pytest.fixture
def no_network(monkeypatch):
    """v55: forces the batched get_daily_data_batch() path empty so every
    cold symbol falls through to the single-ticker get_daily_data()
    fallback this fixture records, with ProcessPoolExecutor faked so
    _run_bounded never touches a real subprocess -- see
    test_crawl_cache_first.py's identical fixture."""
    calls = []

    def _fake(ticker, period=None):
        calls.append(ticker)
        return make_ohlcv([10.0, 11.0, 12.0])

    monkeypatch.setattr(fetch, "get_daily_data", _fake)
    monkeypatch.setattr(fetch, "get_daily_data_batch", lambda tickers, period=None: {})
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlineProcessPool)
    return calls


def test_warm_sector_etfs_cost_no_network(monkeypatch, no_network):
    cached = make_ohlcv([50.0, 51.0, 52.0])
    monkeypatch.setattr(fetch, "_load_cached_daily", lambda t: cached)

    frames = scan_engine._fetch_frames(["XLK", "XLF", "XLE"])

    assert set(frames) == {"XLK", "XLF", "XLE"}
    assert no_network == []


def test_cold_sector_etfs_still_fetch(monkeypatch, no_network):
    monkeypatch.setattr(fetch, "_load_cached_daily", lambda t: None)

    frames = scan_engine._fetch_frames(["XLK", "XLF"])

    assert sorted(no_network) == ["XLF", "XLK"]
    assert set(frames) == {"XLK", "XLF"}


def test_a_failing_etf_is_absent_not_fatal(monkeypatch):
    def _flaky(ticker, period=None):
        raise ValueError("no data")

    monkeypatch.setattr(fetch, "get_daily_data", _flaky)
    monkeypatch.setattr(fetch, "get_daily_data_batch", lambda tickers, period=None: {})
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlineProcessPool)
    monkeypatch.setattr(fetch, "_load_cached_daily", lambda t: None)

    frames = scan_engine._fetch_frames(["XLK"])

    assert frames == {}


def test_daily_frame_for_prefers_cache(monkeypatch, no_network):
    cached = make_ohlcv([400.0, 401.0])
    monkeypatch.setattr(fetch, "_load_cached_daily", lambda t: cached)

    df = scan_engine._daily_frame_for("SPY")

    assert df.equals(cached)
    assert no_network == []


def test_daily_frame_for_falls_back_to_fetch(monkeypatch, no_network):
    monkeypatch.setattr(fetch, "_load_cached_daily", lambda t: None)

    df = scan_engine._daily_frame_for("SPY")

    assert df is not None
    assert no_network == ["SPY"]
