"""The opex calendar is pure date arithmetic -- no network, no mocking.

The two holiday collisions asserted here are real and were verified against
the NYSE calendar: 2026-06-19 (Juneteenth) and 2030-04-19 (Good Friday) are
both the nominal third Friday of their month AND full-day closures, so the
expiration moves to the preceding Thursday in each case.
"""
import datetime as dt

import pytest

from swingbot.core.market import opex


def d(iso: str) -> dt.date:
    return dt.date.fromisoformat(iso)


@pytest.mark.parametrize("iso", [
    "2026-08-21",   # 3rd Friday of Aug 2026
    "2026-01-16",   # 3rd Friday of Jan 2026 (month starting on a Thursday)
    "2026-05-15",   # 3rd Friday of May 2026 (month starting on a Friday)
    "2027-01-15",
])
def test_monthly_third_friday(iso):
    assert opex.opex_tier(d(iso)) == opex.MONTHLY


@pytest.mark.parametrize("iso", ["2026-08-07", "2026-08-14", "2026-08-28"])
def test_other_fridays_are_weekly(iso):
    assert opex.opex_tier(d(iso)) == opex.WEEKLY


@pytest.mark.parametrize("iso", [
    "2026-08-20",   # Thursday
    "2026-08-24",   # Monday
    "2026-08-22",   # Saturday
    "2026-08-23",   # Sunday
])
def test_non_fridays_are_none(iso):
    assert opex.opex_tier(d(iso)) is None


def test_holiday_third_friday_shifts_to_thursday():
    # Juneteenth 2026 falls on Friday 19 June, which is also the nominal
    # third Friday. The market is shut, so expiration moves to Thursday.
    assert opex.opex_tier(d("2026-06-19")) is None
    assert opex.opex_tier(d("2026-06-18")) == opex.MONTHLY
    assert opex.monthly_expiration(2026, 6) == d("2026-06-18")


def test_good_friday_third_friday_shifts_to_thursday():
    # Good Friday 2030 is 19 April, the third Friday of that month.
    assert opex.opex_tier(d("2030-04-19")) is None
    assert opex.opex_tier(d("2030-04-18")) == opex.MONTHLY


def test_holiday_friday_that_is_not_third_friday_is_not_weekly():
    # Good Friday 2026 (3 April) is the FIRST Friday. The market is shut, so
    # it is not a weekly expiration either.
    assert opex.opex_tier(d("2026-04-03")) is None
    assert opex.opex_tier(d("2026-04-17")) == opex.MONTHLY   # unaffected


def test_thursday_before_an_ordinary_holiday_friday_is_not_monthly():
    # 2026-07-03 is a closure (Independence Day observed) but the third
    # Friday of July 2026 is the 17th, so 2026-07-02 must stay None.
    assert opex.opex_tier(d("2026-07-02")) is None


def test_monthly_expiration_is_a_thursday_or_friday_every_month():
    for year in range(2026, 2031):
        for month in range(1, 13):
            got = opex.monthly_expiration(year, month)
            assert got.weekday() in (3, 4), (year, month, got)
            assert got.month == month
