"""v162 AH6: yearly Alpaca windows, retry through the guards, store-frame conversion."""
from __future__ import annotations

import itertools
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from alpaca_history import fetch, guards
from swingbot.core.marketdata.providers import alpaca_provider as ap

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def _jump_clock():
    ticks = itertools.count(0.0, 60.0)
    return lambda: next(ticks)


def _limiter():
    return guards.TokenBucket(clock=_jump_clock(), sleep=lambda s: None)


def _raw(ny_stamps: list[str], close: float = 10.5) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(s, tz=NY) for s in ny_stamps]).tz_convert("UTC")
    n = len(idx)
    return pd.DataFrame({"open": [10.0] * n, "high": [11.0] * n, "low": [9.0] * n,
                         "close": [close] * n, "volume": [100.0] * n}, index=idx)


class FakeProvider:
    """Serves one raw frame per Alpaca timeframe, sliced to [start, end]
    (or whole, when `ignore_window` is set, to mimic a bar repeated at a boundary)."""

    def __init__(self, frames: dict[str, pd.DataFrame], errors: list[Exception] | None = None,
                 ignore_window: bool = False):
        self.frames = frames
        self.errors = list(errors or [])
        self.ignore_window = ignore_window
        self.calls: list[tuple[str, str, datetime, datetime]] = []

    def history_bars(self, ticker, timeframe, start, end):
        self.calls.append((ticker, timeframe, start, end))
        if self.errors:
            raise self.errors.pop(0)
        frame = self.frames.get(timeframe)
        if frame is None:
            return None
        if self.ignore_window:
            return frame
        part = frame[(frame.index >= start) & (frame.index <= end)]
        return part if len(part) else None


class _Http(Exception):
    def __init__(self, code):
        super().__init__(str(code))
        self.status_code = code


def _wrapped(cls, code: int):
    try:
        raise cls(str(code)) from _Http(code)
    except cls as exc:
        return exc


def test_year_windows_cover_calendar_years_and_stop_at_end():
    end = datetime(2018, 3, 5, 12, 0, tzinfo=UTC)
    windows = fetch.year_windows(date(2016, 1, 1), end)
    assert windows == [
        (datetime(2016, 1, 1, tzinfo=UTC), datetime(2017, 1, 1, tzinfo=UTC)),
        (datetime(2017, 1, 1, tzinfo=UTC), datetime(2018, 1, 1, tzinfo=UTC)),
        (datetime(2018, 1, 1, tzinfo=UTC), end),
    ]


def test_year_windows_start_mid_year_and_naive_end_is_utc():
    windows = fetch.year_windows(date(2016, 6, 15), datetime(2016, 9, 1))
    assert windows == [(datetime(2016, 6, 15, tzinfo=UTC), datetime(2016, 9, 1, tzinfo=UTC))]


def test_year_windows_empty_when_end_not_after_start():
    assert fetch.year_windows(date(2020, 1, 1), datetime(2020, 1, 1, tzinfo=UTC)) == []


def test_fetch_raw_calls_once_per_year_with_the_alpaca_timeframe():
    raw30 = _raw(["2016-03-01 09:30", "2016-03-01 10:00", "2017-03-01 09:30"])
    prov = FakeProvider({"30min": raw30})
    out = fetch.fetch_raw(prov, "AAPL", "hourly", date(2016, 1, 1),
                          datetime(2017, 6, 1, tzinfo=UTC), limiter=_limiter())
    assert [c[1] for c in prov.calls] == ["30min", "30min"]
    assert len(out) == 3 and out.index.is_monotonic_increasing


def test_fetch_raw_drops_a_bar_returned_by_two_windows():
    prov = FakeProvider({"1d": _raw(["2016-12-30 00:00"])}, ignore_window=True)
    out = fetch.fetch_raw(prov, "AAPL", "daily", date(2016, 1, 1),
                          datetime(2017, 2, 1, tzinfo=UTC), limiter=_limiter())
    assert len(prov.calls) == 2
    assert len(out) == 1


def test_fetch_raw_returns_none_when_no_window_has_bars():
    prov = FakeProvider({})
    assert fetch.fetch_raw(prov, "AAPL", "15min", date(2016, 1, 1),
                           datetime(2018, 1, 2, tzinfo=UTC), limiter=_limiter()) is None
    assert len(prov.calls) == 3


def test_fetch_raw_retries_a_rate_limit_through_call_with_backoff():
    sleeps: list[float] = []
    prov = FakeProvider({"1d": _raw(["2016-03-01 00:00"])}, errors=[_wrapped(ap.AlpacaMiss, 429)])
    out = fetch.fetch_raw(prov, "AAPL", "daily", date(2016, 1, 1),
                          datetime(2016, 6, 1, tzinfo=UTC), limiter=_limiter(), sleep=sleeps.append)
    assert len(out) == 1
    assert len(sleeps) == 1 and len(prov.calls) == 2


def test_fetch_raw_stops_on_auth_error():
    prov = FakeProvider({}, errors=[_wrapped(ap.AlpacaAuthError, 401)])
    with pytest.raises(ap.AlpacaAuthError):
        fetch.fetch_raw(prov, "AAPL", "daily", date(2016, 1, 1),
                        datetime(2016, 6, 1, tzinfo=UTC), limiter=_limiter(), sleep=lambda s: None)
    assert len(prov.calls) == 1


def test_unknown_timeframe_raises_before_any_request():
    prov = FakeProvider({})
    with pytest.raises(ValueError):
        fetch.fetch_raw(prov, "AAPL", "1Hour", date(2016, 1, 1),
                        datetime(2017, 1, 1, tzinfo=UTC), limiter=_limiter())
    assert prov.calls == []
    with pytest.raises(ValueError):
        fetch.to_store_frame("weekly", _raw(["2016-03-01 09:30"]))


def test_to_store_frame_daily_is_a_naive_date_index():
    out = fetch.to_store_frame("daily", _raw(["2016-03-01 00:00", "2016-03-02 00:00"]))
    assert out.index.name == "Date" and out.index.tz is None
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert [d.isoformat() for d in out.index.date] == ["2016-03-01", "2016-03-02"]


def test_to_store_frame_15min_keeps_extended_hours_as_ny_wall_clock():
    out = fetch.to_store_frame("15min", _raw(["2016-03-01 04:00", "2016-03-01 09:30",
                                              "2016-03-01 19:45"]))
    assert out.index.name == "Datetime" and out.index.tz is None
    assert [t.strftime("%H:%M") for t in out.index] == ["04:00", "09:30", "19:45"]


def test_to_store_frame_hourly_is_built_from_30min_rth_bars():
    out = fetch.to_store_frame("hourly", _raw(["2016-03-01 08:00", "2016-03-01 09:30",
                                               "2016-03-01 10:00", "2016-03-01 15:30"]))
    assert out.index.name == "Datetime" and out.index.tz is None
    assert [t.strftime("%H:%M") for t in out.index] == ["09:30", "15:30"]
    assert out["Volume"].iloc[0] == 200.0


def test_fetch_store_frame_converts_or_returns_none():
    prov = FakeProvider({"15min": _raw(["2016-03-01 09:30", "2016-03-01 09:45"])})
    out = fetch.fetch_store_frame(prov, "AAPL", "15min", date(2016, 1, 1),
                                  datetime(2016, 6, 1, tzinfo=UTC), limiter=_limiter())
    assert out.index.name == "Datetime" and len(out) == 2
    assert fetch.fetch_store_frame(FakeProvider({}), "AAPL", "daily", date(2016, 1, 1),
                                   datetime(2016, 6, 1, tzinfo=UTC), limiter=_limiter()) is None
