import datetime as dt

import pytest

from swingbot.core.market.session import (
    US_MARKET_TZ,
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