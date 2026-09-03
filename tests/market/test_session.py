import datetime as dt

import pytest

from swingbot.core.market.session import (
    US_MARKET_TZ,
    is_quiet_hours,
    is_regular_session,
    now_et,
    session_date,
)


def _et(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm, tzinfo=US_MARKET_TZ)


@pytest.mark.parametrize(("moment", "expected"), [
    (_et(2026, 8, 27, 9, 29), False),
    (_et(2026, 8, 27, 9, 30), True),
    (_et(2026, 8, 27, 12, 0), True),
    (_et(2026, 8, 27, 15, 59), True),
    (_et(2026, 8, 27, 16, 0), False),
    (_et(2026, 8, 27, 4, 15), False),
    (_et(2026, 8, 27, 19, 30), False),
    (_et(2026, 8, 29, 12, 0), False),
    (_et(2026, 8, 30, 12, 0), False),
])
def test_regular_session_boundaries(moment, expected):
    assert is_regular_session(moment) is expected


def test_naive_and_utc_inputs_are_converted_to_et():
    utc = dt.datetime(2026, 8, 27, 20, 0, tzinfo=dt.timezone.utc)
    assert is_regular_session(utc) is False
    assert is_regular_session(
        dt.datetime(2026, 8, 27, 18, 0, tzinfo=dt.timezone.utc)
    ) is True


def test_session_date_is_the_et_calendar_day_not_the_utc_one():
    assert session_date(_et(2026, 8, 27, 22, 0)) == "2026-08-27"
    utc_next_day = dt.datetime(2026, 8, 28, 2, 0, tzinfo=dt.timezone.utc)
    assert session_date(utc_next_day) == "2026-08-27"


def test_now_et_defaults_to_the_current_moment_in_et():
    assert now_et().tzinfo is US_MARKET_TZ


@pytest.mark.parametrize(("moment", "expected"), [
    (_et(2026, 8, 27, 22, 59), False),
    (_et(2026, 8, 27, 23, 0), True),
    (_et(2026, 8, 27, 2, 0), True),
    (_et(2026, 8, 27, 7, 59), True),
    (_et(2026, 8, 27, 8, 0), False),
    (_et(2026, 8, 27, 12, 0), False),
    (_et(2026, 8, 27, 19, 30), False),
])
def test_quiet_hours_boundaries(moment, expected):
    assert is_quiet_hours(moment) is expected


@pytest.mark.parametrize("hour", list(range(24)))
def test_every_hour_of_the_weekend_is_quiet(hour):
    assert is_quiet_hours(_et(2026, 8, 29, hour, 0)) is True   # Saturday
    assert is_quiet_hours(_et(2026, 8, 30, hour, 0)) is True   # Sunday


def test_quiet_hours_never_overlaps_the_regular_session():
    for hour, minute in ((9, 30), (12, 0), (15, 59)):
        moment = _et(2026, 8, 27, hour, minute)
        assert is_regular_session(moment) is True
        assert is_quiet_hours(moment) is False


def test_the_window_is_read_from_config(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "QUIET_HOURS_START_ET", 20)
    monkeypatch.setattr(config, "QUIET_HOURS_END_ET", 6)
    assert is_quiet_hours(_et(2026, 8, 27, 19, 59)) is False
    assert is_quiet_hours(_et(2026, 8, 27, 20, 0)) is True
    assert is_quiet_hours(_et(2026, 8, 27, 5, 59)) is True
    assert is_quiet_hours(_et(2026, 8, 27, 6, 0)) is False


def test_a_utc_input_is_converted_before_the_window_is_applied():
    # 2026-08-28 02:00 UTC is 2026-08-27 22:00 ET -- a Thursday evening, one
    # hour before the window opens, not the small hours of Friday morning.
    utc = dt.datetime(2026, 8, 28, 2, 0, tzinfo=dt.timezone.utc)
    assert is_quiet_hours(utc) is False