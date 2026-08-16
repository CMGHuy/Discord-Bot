"""get_next_earnings_datetime -- the timezone-aware companion to
get_next_earnings_date, added for the Watchlist Earnings calendar.

No prior test file existed for events.py; get_next_earnings_date itself is
only exercised indirectly today (tests/admin/test_api_v1_watchlist.py,
tests/edge/gate tests). This covers the new function directly since it
carries real timezone-conversion logic worth verifying on its own.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from swingbot.core.market import events


def _earnings_index(*timestamps: dt.datetime) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(timestamps, name="Earnings Date")


def _frame(*timestamps: dt.datetime) -> pd.DataFrame:
    # A real yfinance response always carries EPS Estimate/Reported EPS/
    # Surprise(%) columns. This matters here, not just for realism: a
    # DataFrame with an index but ZERO columns reports .empty == True
    # regardless of index length (df.size == len(index) * len(columns)),
    # which silently swallowed every entry the first time this fixture was
    # written with no columns at all.
    return pd.DataFrame({"EPS Estimate": [1.0] * len(timestamps)},
                        index=_earnings_index(*timestamps))


class _FakeTicker:
    def __init__(self, frame: pd.DataFrame):
        self._frame = frame

    def get_earnings_dates(self, limit=6):
        return self._frame


@pytest.fixture(autouse=True)
def not_an_etf(monkeypatch):
    monkeypatch.setattr(events, "is_etf", lambda t: False)


@pytest.fixture(autouse=True)
def one_candidate(monkeypatch):
    # candidate_symbols normally yields format variants; pin it to the
    # ticker itself so tests control exactly one yfinance call.
    monkeypatch.setattr(events, "candidate_symbols", lambda t: [t])


def test_returns_the_nearest_future_timestamp(monkeypatch):
    tz = dt.timezone(dt.timedelta(hours=-4))  # America/New_York, EDT
    past = dt.datetime(2020, 1, 1, 16, 0, tzinfo=tz)
    near_future = dt.datetime(2026, 10, 29, 16, 0, tzinfo=tz)
    far_future = dt.datetime(2027, 1, 28, 16, 0, tzinfo=tz)
    frame = _frame(far_future, past, near_future)  # deliberately unsorted
    monkeypatch.setattr(events.yf, "Ticker", lambda symbol: _FakeTicker(frame))

    result = events.get_next_earnings_datetime("AAPL")

    assert result == near_future


def test_returns_none_when_every_entry_is_in_the_past(monkeypatch):
    tz = dt.timezone(dt.timedelta(hours=-4))
    frame = _frame(dt.datetime(2020, 1, 1, 16, 0, tzinfo=tz))
    monkeypatch.setattr(events.yf, "Ticker", lambda symbol: _FakeTicker(frame))

    assert events.get_next_earnings_datetime("AAPL") is None


def test_returns_none_when_yfinance_has_nothing(monkeypatch):
    monkeypatch.setattr(events.yf, "Ticker", lambda symbol: _FakeTicker(pd.DataFrame()))

    assert events.get_next_earnings_datetime("AAPL") is None


def test_returns_none_for_an_etf(monkeypatch):
    monkeypatch.setattr(events, "is_etf", lambda t: True)

    def boom(symbol):
        raise AssertionError("must not fetch calendar data for an ETF")

    monkeypatch.setattr(events.yf, "Ticker", boom)

    assert events.get_next_earnings_datetime("SPY") is None


def test_a_fetch_exception_is_swallowed(monkeypatch):
    def boom(symbol):
        raise RuntimeError("network hiccup")

    monkeypatch.setattr(events.yf, "Ticker", boom)

    assert events.get_next_earnings_datetime("AAPL") is None


def test_the_returned_datetime_converts_correctly_to_utc(monkeypatch):
    # 16:00 EDT (UTC-4) is 20:00 UTC -- the exact AAPL case from manual
    # verification against the real yfinance API.
    tz = dt.timezone(dt.timedelta(hours=-4))
    upcoming = dt.datetime(2026, 10, 29, 16, 0, tzinfo=tz)
    frame = _frame(upcoming)
    monkeypatch.setattr(events.yf, "Ticker", lambda symbol: _FakeTicker(frame))

    result = events.get_next_earnings_datetime("AAPL")

    assert result.astimezone(dt.timezone.utc) == dt.datetime(
        2026, 10, 29, 20, 0, tzinfo=dt.timezone.utc)
