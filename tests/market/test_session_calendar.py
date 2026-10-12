import datetime as dt

import pandas as pd
import pytest

from swingbot.core.market import opex
from swingbot.core.market.session import NYSE_HOLIDAYS, NYSE_LAST_YEAR_COVERED, SessionCalendar, nyse_calendar

D = dt.date.fromisoformat


def test_sessions_between_rolls_dates_to_trading_sessions():
    cal = nyse_calendar()
    assert cal.sessions_between(D("2026-09-11"), D("2026-09-14")) == 1
    assert cal.sessions_between(D("2026-09-14"), D("2026-09-14")) == 0
    assert cal.sessions_between(D("2026-11-25"), D("2026-11-27")) == 1
    assert cal.sessions_between(D("2026-09-12"), D("2026-09-14")) == 1
    assert cal.sessions_between(D("2026-09-11"), D("2026-09-13")) == 1


def test_calendar_skips_holidays_and_has_a_complete_opex_subset():
    cal = nyse_calendar()
    assert cal.next_session(D("2026-07-02")) == D("2026-07-06")
    assert cal.is_session(D("2026-09-14"))
    assert not cal.is_session(D("2026-09-12"))
    assert not cal.is_session(D("2026-11-26"))
    assert all(d.weekday() < 5 for d in NYSE_HOLIDAYS)
    assert opex._FRIDAY_HOLIDAYS == {d for d in NYSE_HOLIDAYS if d.weekday() == 4 and d.year >= 2026}
    assert dt.date.today() <= dt.date(NYSE_LAST_YEAR_COVERED, 12, 31) - dt.timedelta(days=90)


def test_bar_index_constructor_and_empty_calendar():
    cal = SessionCalendar.from_bar_index(pd.DatetimeIndex(["2026-01-02", "2026-01-05"]))
    assert len(cal) == 2
    assert cal.first == D("2026-01-02") and cal.last == D("2026-01-05")
    assert cal.sessions_between(D("2026-01-02"), D("2026-01-05")) == 1
    assert cal.position_on_or_after(D("2026-01-06")) is None
    assert cal.position_on_or_before(D("2026-01-01")) is None
    with pytest.raises(ValueError):
        SessionCalendar([])


# --- v151: session_after -------------------------------------------------

def test_session_after_zero_is_the_session_itself_or_the_one_before():
    cal = nyse_calendar()
    assert cal.session_after(D("2026-09-14"), 0) == D("2026-09-14")   # a Monday session
    assert cal.session_after(D("2026-09-12"), 0) == D("2026-09-11")   # Saturday rolls back to Friday


def test_session_after_counts_sessions_not_calendar_days():
    cal = nyse_calendar()
    # Mon 14 Sep + 5 sessions: 15, 16, 17, 18, 21.
    assert cal.session_after(D("2026-09-14"), 5) == D("2026-09-21")
    # Thanksgiving (Thu 26 Nov 2026) is skipped.
    assert cal.session_after(D("2026-11-25"), 1) == D("2026-11-27")


def test_session_after_matches_the_time_exit_tenth_session():
    from swingbot.core.planning.time_exit import tenth_session
    cal = nyse_calendar()
    fill = D("2026-09-15")
    assert cal.session_after(fill, 9) == tenth_session(fill, cal) == D("2026-09-28")


@pytest.mark.parametrize("day, n", [
    (D("2026-09-14"), -1),          # negative count
    (D("2017-12-29"), 0),           # before the calendar's first session
    (D("2031-01-02"), 0),           # after the calendar's last session
    (D("2030-12-30"), 5),           # result runs past coverage
])
def test_session_after_is_none_outside_coverage(day, n):
    assert nyse_calendar().session_after(day, n) is None


def test_session_after_on_a_small_calendar():
    cal = SessionCalendar([D("2026-01-05"), D("2026-01-06"), D("2026-01-08")])
    assert cal.session_after(D("2026-01-07"), 1) == D("2026-01-08")
    assert cal.session_after(D("2026-01-05"), 2) == D("2026-01-08")
    assert cal.session_after(D("2026-01-05"), 3) is None
