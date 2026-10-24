"""v184: NYSE regular sessions used by the monitor's market_open stamp."""
import datetime as dt

import pytest

from swingbot.core.market import session
from swingbot.core.market.session import US_MARKET_TZ, is_nyse_regular_session


def _et(y, m, d, hh, mm, ss=0):
    return dt.datetime(y, m, d, hh, mm, ss, tzinfo=US_MARKET_TZ)


@pytest.mark.parametrize("when, expected", [
    (_et(2026, 10, 21, 10, 0), True),
    (_et(2026, 10, 21, 9, 29, 59), False),
    (_et(2026, 10, 21, 9, 30), True),
    (_et(2026, 10, 21, 15, 59, 59), True),
    (_et(2026, 10, 21, 16, 0), False),
    (_et(2026, 10, 21, 20, 0), False),
])
def test_ordinary_weekday_follows_rth(when, expected):
    assert is_nyse_regular_session(when) is expected


def test_weekend_is_closed_even_inside_rth_hours():
    # NYSE_HOLIDAYS holds no weekends, so checking that table alone is wrong.
    assert is_nyse_regular_session(_et(2026, 10, 24, 11, 0)) is False
    assert is_nyse_regular_session(_et(2026, 10, 25, 11, 0)) is False


def test_full_day_holiday_is_closed():
    thanksgiving = _et(2026, 11, 26, 11, 0)
    assert dt.date(2026, 11, 26) in session.NYSE_HOLIDAYS
    assert is_nyse_regular_session(thanksgiving) is False
    assert session.is_regular_session(thanksgiving) is True


@pytest.mark.parametrize("when, expected", [
    (_et(2026, 11, 27, 12, 59, 59), True),
    (_et(2026, 11, 27, 13, 0), False),
    (_et(2026, 11, 27, 14, 30), False),
    (_et(2026, 12, 24, 13, 30), False),
])
def test_half_day_closes_at_one_pm(when, expected):
    assert is_nyse_regular_session(when) is expected


def test_utc_input_is_converted_to_new_york_time():
    # 13:30 UTC on 2026-10-21 is 09:30 EDT.
    open_utc = dt.datetime(2026, 10, 21, 13, 30, tzinfo=dt.timezone.utc)
    assert is_nyse_regular_session(open_utc) is True
    assert is_nyse_regular_session(open_utc - dt.timedelta(seconds=1)) is False


def test_naive_input_is_read_as_new_york_wall_clock():
    assert is_nyse_regular_session(dt.datetime(2026, 10, 21, 10, 0)) is True


def test_default_reads_the_clock(monkeypatch):
    monkeypatch.setattr(session, "now_et",
                        lambda now=None: _et(2026, 11, 26, 11, 0) if now is None else now)
    assert is_nyse_regular_session() is False
