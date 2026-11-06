"""v208 V208-8: account closes, session alignment, gaps, base_balance breaks."""
from datetime import date, datetime, timezone
from decimal import Decimal
from itertools import count

import pytest

from swingbot.core.analytics import benchmark_series as bs
from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar
from swingbot.core.tracking.equity import RealizedLeg
from swingbot.core.tracking.equity_candles import mtm_candles

MON, TUE, WED, THU, FRI = (date(2026, 11, d) for d in (2, 3, 4, 5, 6))
WEEK = [MON, TUE, WED, THU, FRI]
_ids = count(1)


def _at(day, hh, mm=0):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=US_MARKET_TZ).astimezone(timezone.utc)


def _row(day, hh, mm, equity, *, realized=None, source="live", kind="point"):
    return {"id": next(_ids), "at": _at(day, hh, mm), "equity": equity,
            "realized_balance": equity if realized is None else realized,
            "unrealized_pnl": 0.0, "open_n": 0, "skipped_n": 0, "source": source, "kind": kind}


def _book():
    return [
        _row(MON, 9, 30, 10_000.0, source="backfill"), _row(MON, 16, 0, 10_100.0, source="backfill"),
        _row(MON, 9, 30, 10_400.0, source="backfill", kind="day_high"),
        _row(TUE, 9, 35, 10_120.0), _row(TUE, 15, 55, 10_201.0),
        _row(TUE, 9, 35, 9_000.0, kind="day_low"),
        _row(WED, 10, 0, 10_150.0), _row(WED, 15, 55, 10_098.99),
    ]


def test_daily_closes_equal_the_dashboard_1d_closes():
    rows = _book()
    dashboard = {date.fromisoformat(c["t"]): c["c"] for c in mtm_candles(rows, "1D")}
    assert bs.bot_session_closes(rows, WEEK) == dashboard
    assert bs.bot_session_closes(rows, WEEK) == {MON: 10_100.0, TUE: 10_201.0, WED: 10_098.99}


def test_a_holiday_live_sample_never_becomes_a_session():
    wed, thanksgiving, fri = date(2026, 11, 25), date(2026, 11, 26), date(2026, 11, 27)
    sessions = nyse_calendar().sessions(wed, fri)
    assert thanksgiving not in sessions
    rows = [_row(wed, 15, 55, 10_000.0), _row(thanksgiving, 11, 0, 10_500.0), _row(fri, 12, 55, 10_050.0)]
    assert bs.bot_session_closes(rows, sessions) == {wed: 10_000.0, fri: 10_050.0}


def test_a_weekend_backfill_candle_is_skipped():
    sat = date(2026, 11, 7)
    rows = [_row(FRI, 16, 0, 10_000.0, source="backfill"), _row(sat, 16, 0, 10_300.0, source="backfill")]
    assert bs.bot_session_closes(rows, WEEK) == {FRI: 10_000.0}


SPY = {MON: (0.001, False), TUE: (0.01, False), WED: (0.02, True), THU: (-0.01, False), FRI: (0.005, False)}


def test_one_session_days_pair_with_the_index_day():
    days = bs.align(WEEK, {MON: 100.0, TUE: 101.0, WED: 102.01, THU: 101.0, FRI: 102.0}, {"SPY": SPY}, set())
    assert [d.session for d in days] == WEEK
    first, tue = days[0], days[1]
    assert (first.bot_ret, first.span, first.one_session) == (None, 1, False)
    assert first.index_ret == {"SPY": 0.001}
    assert tue.bot_ret == pytest.approx(0.01) and tue.span == 1 and tue.one_session
    assert tue.index_ret == {"SPY": 0.01} and tue.index_proxy == {"SPY": False}


def test_a_missing_bot_session_is_a_gap_and_the_index_compounds_over_the_span():
    days = bs.align(WEEK, {MON: 100.0, TUE: 101.0, THU: 103.02, FRI: 104.0}, {"SPY": SPY}, set())
    wed, thu = days[2], days[3]
    assert wed.missing and wed.bot_close is None and wed.bot_ret is None
    assert wed.index_ret == {"SPY": None} and wed.index_proxy == {"SPY": True}
    assert not wed.one_session
    assert thu.span == 2 and not thu.missing and not thu.one_session
    assert thu.bot_ret == pytest.approx(103.02 / 101.0 - 1)
    assert thu.index_ret["SPY"] == pytest.approx(1.02 * 0.99 - 1)
    assert thu.index_proxy == {"SPY": True}
    assert days[4].span == 1 and days[4].one_session


def test_a_span_with_an_unpriced_index_day_has_no_index_return():
    spy = {day: value for day, value in SPY.items() if day != WED}
    days = bs.align(WEEK, {MON: 100.0, TUE: 101.0, THU: 103.0}, {"SPY": spy}, set())
    assert days[3].span == 2 and days[3].index_ret == {"SPY": None}


def test_sessions_before_the_first_close_are_missing_and_open_no_span():
    days = bs.align(WEEK, {WED: 100.0, THU: 101.0}, {"SPY": SPY}, set())
    assert [d.missing for d in days] == [True, True, False, False, True]
    assert (days[2].bot_ret, days[2].span) == (None, 1)
    assert days[3].span == 1 and days[3].one_session


def test_no_closes_at_all_is_every_session_missing():
    assert all(d.missing and d.bot_ret is None for d in bs.align(WEEK, {}, {"SPY": SPY}, set()))


def test_a_base_break_keeps_its_raw_return_but_is_never_one_session():
    days = bs.align(WEEK, {MON: 100.0, TUE: 110.0}, {"SPY": SPY}, {TUE})
    assert days[1].base_break and days[1].bot_ret == pytest.approx(0.1) and not days[1].one_session


def _close(day, realized):
    return _row(day, 15, 55, realized, realized=realized)


@pytest.mark.parametrize("jump, leg, breaks", [
    (500.0, None, {WED}),
    (500.0, Decimal("500"), set()),
    (500.01, Decimal("500"), set()),
    (500.02, Decimal("500"), {WED}),
])
def test_base_balance_breaks(jump, leg, breaks):
    rows = [_close(MON, 10_000.0), _close(TUE, 10_000.0), _close(WED, 10_000.0 + jump)]
    legs = [] if leg is None else [RealizedLeg(_at(WED, 11), leg, "t1")]
    assert bs.base_balance_breaks(rows, legs, WEEK) == breaks


def test_a_leg_before_the_previous_close_does_not_explain_a_jump():
    rows = [_close(TUE, 10_000.0), _close(WED, 10_500.0)]
    legs = [RealizedLeg(_at(TUE, 15, 0), Decimal("500"), "t1")]
    assert bs.base_balance_breaks(rows, legs, WEEK) == {WED}


def test_a_break_is_measured_across_a_missing_session():
    rows = [_close(MON, 10_000.0), _close(WED, 10_300.0)]
    legs = [RealizedLeg(_at(TUE, 12), Decimal("300"), "t1")]
    assert bs.base_balance_breaks(rows, legs, WEEK) == set()
