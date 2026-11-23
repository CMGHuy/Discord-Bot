"""v239 V239-4: the live (s, D) pair and the completed-bar cut. One case per
calendar situation the spec names: weekend, holiday, half-day, and a scan
after the close but before the refresher ran. November 2026: Thanksgiving is
Thu 11-26 (holiday), Fri 11-27 closes at 13:00 ET; Dec 24 closes at 13:00 and
Dec 25 is a holiday."""
import datetime as dt
from datetime import date

import pandas as pd
import pytest

from swingbot.core.market import session
from swingbot.core.scanning import regime_calendar as rc
from swingbot.core.scanning.strategy_pass import completed_frame


def _et(month, day, hour, minute=0):
    return dt.datetime(2026, month, day, hour, minute, tzinfo=session.US_MARKET_TZ)


def _frame(end: date, tz=None) -> pd.DataFrame:
    """Real NYSE sessions (no bar on a holiday) from 2026-01-02 through ``end``."""
    days = session.nyse_calendar().sessions(date(2026, 1, 2), end)
    if not session.nyse_calendar().is_session(end):
        days.append(end)                                   # a stray early bar dated ``end``
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in days], name="Date")
    if tz:
        index = index.tz_localize(tz)
    closes = [float(i) for i in range(len(index))]
    return pd.DataFrame({"High": closes, "Close": closes}, index=index)


@pytest.mark.parametrize("now, s, d", [
    (_et(11, 23, 11), date(2026, 11, 20), date(2026, 11, 23)),     # Monday, in session
    (_et(11, 23, 15, 59), date(2026, 11, 20), date(2026, 11, 23)),
    (_et(11, 23, 16), date(2026, 11, 23), date(2026, 11, 24)),     # the close itself
    (_et(11, 23, 16, 30), date(2026, 11, 23), date(2026, 11, 24)),  # after close, before refresher
    (_et(11, 24, 8), date(2026, 11, 23), date(2026, 11, 24)),      # pre-market
    (_et(11, 21, 12), date(2026, 11, 20), date(2026, 11, 23)),     # Saturday
    (_et(11, 22, 20), date(2026, 11, 20), date(2026, 11, 23)),     # Sunday
    (_et(11, 25, 20), date(2026, 11, 25), date(2026, 11, 27)),     # skips Thanksgiving
    (_et(11, 26, 12), date(2026, 11, 25), date(2026, 11, 27)),     # on the holiday
    (_et(11, 27, 12, 59), date(2026, 11, 25), date(2026, 11, 27)),  # half-day, before 13:00
    (_et(11, 27, 13), date(2026, 11, 27), date(2026, 11, 30)),     # half-day, at its close
    (_et(11, 27, 14), date(2026, 11, 27), date(2026, 11, 30)),     # half-day, after its close
    (_et(12, 24, 14), date(2026, 12, 24), date(2026, 12, 28)),     # Dec 24 half-day, Dec 25 shut
])
def test_session_pair(now, s, d):
    assert rc.session_pair(now) == (s, d)


def test_session_pair_reads_a_utc_clock():
    now = dt.datetime(2026, 11, 23, 21, 30, tzinfo=dt.timezone.utc)   # 16:30 ET
    assert rc.session_pair(now) == (date(2026, 11, 23), date(2026, 11, 24))


def test_an_intraday_partial_bar_is_cut():
    df = _frame(date(2026, 11, 23))
    out = rc.cut_completed(df, _et(11, 23, 11))
    assert out.index[-1] == pd.Timestamp("2026-11-20")
    pd.testing.assert_frame_equal(out, df.iloc[:-1])


def test_after_the_close_the_session_bar_is_kept():
    df = _frame(date(2026, 11, 23))
    pd.testing.assert_frame_equal(rc.cut_completed(df, _et(11, 23, 16, 30)), df)


def test_a_half_day_bar_counts_as_completed_after_the_early_close():
    df = _frame(date(2026, 11, 27))
    now = _et(11, 27, 14)
    pd.testing.assert_frame_equal(rc.cut_completed(df, now), df)
    # why completed_frame alone is not enough: it is blind to the 13:00 close
    assert len(completed_frame(df, now)) == len(df) - 1


def test_a_half_day_bar_is_cut_before_the_early_close():
    out = rc.cut_completed(_frame(date(2026, 11, 27)), _et(11, 27, 12))
    assert out.index[-1] == pd.Timestamp("2026-11-25")


def test_a_premarket_bar_dated_today_is_cut():
    out = rc.cut_completed(_frame(date(2026, 11, 24)), _et(11, 24, 8))
    assert out.index[-1] == pd.Timestamp("2026-11-23")


def test_a_weekend_bar_is_cut():
    out = rc.cut_completed(_frame(date(2026, 11, 21)), _et(11, 21, 12))      # stray Saturday bar
    assert out.index[-1] == pd.Timestamp("2026-11-20")


@pytest.mark.parametrize("end, now", [
    (date(2026, 11, 23), _et(11, 23, 11)),
    (date(2026, 11, 23), _et(11, 23, 16, 30)),
    (date(2026, 11, 23), _et(11, 24, 8)),
    (date(2026, 11, 20), _et(11, 21, 12)),
])
def test_on_regular_days_the_cut_equals_completed_frame(end, now):
    df = _frame(end)
    pd.testing.assert_frame_equal(rc.cut_completed(df, now), completed_frame(df, now))


def test_a_tz_aware_index_is_cut_by_its_wall_date():
    naive, aware = _frame(date(2026, 11, 23)), _frame(date(2026, 11, 23), tz="UTC")
    now = _et(11, 23, 11)
    assert list(rc.cut_completed(aware, now).index.date) == list(rc.cut_completed(naive, now).index.date)


@pytest.mark.parametrize("df", [None, pd.DataFrame({"Close": []})])
def test_nothing_to_cut_is_returned_unchanged(df):
    assert rc.cut_completed(df, _et(11, 23, 11)) is df


@pytest.mark.parametrize("older, newer, n", [
    (date(2026, 11, 20), date(2026, 11, 23), 1),
    (date(2026, 11, 25), date(2026, 11, 27), 1),     # Thanksgiving is not a session
    (date(2026, 11, 13), date(2026, 11, 23), 6),
    (date(2026, 11, 20), date(2026, 11, 30), 5),
    (date(2026, 11, 20), date(2026, 11, 20), 0),
    (date(2026, 11, 23), date(2026, 11, 20), 0),
])
def test_sessions_between(older, newer, n):
    assert rc.sessions_between(older, newer) == n
