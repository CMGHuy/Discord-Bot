"""v47: SPY and the sector ETFs come from the cache too.

They are ~12 further sequential fetches per scan on top of the watchlist crawl.
"""
import pytest

from swingbot.core.scanning import engine as scan_engine
from tests.helpers import make_ohlcv


@pytest.fixture
def no_network(monkeypatch):
    calls = []

    def _fake(ticker, period=None):
        calls.append(ticker)
        return make_ohlcv([10.0, 11.0, 12.0])

    monkeypatch.setattr(scan_engine, "get_daily_data", _fake)
    return calls


def test_warm_sector_etfs_cost_no_network(monkeypatch, no_network):
    cached = make_ohlcv([50.0, 51.0, 52.0])
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: cached)

    frames = scan_engine._fetch_frames(["XLK", "XLF", "XLE"])

    assert set(frames) == {"XLK", "XLF", "XLE"}
    assert no_network == []


def test_cold_sector_etfs_still_fetch(monkeypatch, no_network):
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    frames = scan_engine._fetch_frames(["XLK", "XLF"])

    assert sorted(no_network) == ["XLF", "XLK"]
    assert set(frames) == {"XLK", "XLF"}


def test_a_failing_etf_is_absent_not_fatal(monkeypatch):
    def _flaky(ticker, period=None):
        raise ValueError("no data")

    monkeypatch.setattr(scan_engine, "get_daily_data", _flaky)
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    frames = scan_engine._fetch_frames(["XLK"])

    assert frames == {}


def test_daily_frame_for_prefers_cache(monkeypatch, no_network):
    cached = make_ohlcv([400.0, 401.0])
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: cached)

    df = scan_engine._daily_frame_for("SPY")

    assert df.equals(cached)
    assert no_network == []


def test_daily_frame_for_falls_back_to_fetch(monkeypatch, no_network):
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    df = scan_engine._daily_frame_for("SPY")

    assert df is not None
    assert no_network == ["SPY"]
