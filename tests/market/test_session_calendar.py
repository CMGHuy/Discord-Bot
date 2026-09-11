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
