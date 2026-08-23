"""Policy layer: config + tier -> the numbers the scan pipeline uses.

Time is always injected. Nothing here reads the wall clock, so these tests
do not change behaviour on a real opex day.
"""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market import opex

MONTHLY_DAY = dt.datetime(2026, 8, 21, 12, 0, tzinfo=opex.US_MARKET_TZ)   # 3rd Fri
WEEKLY_DAY = dt.datetime(2026, 8, 14, 12, 0, tzinfo=opex.US_MARKET_TZ)    # plain Fri
PLAIN_DAY = dt.datetime(2026, 8, 20, 12, 0, tzinfo=opex.US_MARKET_TZ)     # Thursday


@pytest.fixture
def opex_on(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 4)
    monkeypatch.setattr(config, "OPEX_MONTHLY_CONFIDENCE_BUMP", 1)
    monkeypatch.setattr(config, "OPEX_MONTHLY_CONFLUENCE_BUMP", 1)
    monkeypatch.setattr(config, "OPEX_WEEKLY_CONFLUENCE_BUMP", 1)
    monkeypatch.setattr(config, "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES", 60)
    monkeypatch.setattr(config, "OPEX_STOP_WIDEN_PCT", 10.0)
    monkeypatch.setattr(config, "OPEX_SIZE_REDUCTION_PCT", 25.0)


# -- the master switch ---------------------------------------------------

def test_everything_is_inert_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", False)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 4)
    assert opex.current_tier(MONTHLY_DAY) is None
    assert opex.effective_min_confidence_level() == 4
    assert opex.effective_min_confluence(2) == 2
    assert opex.suppress_new_entries(MONTHLY_DAY) is False
    assert opex.stop_mult() == 1.0
    assert opex.size_mult() == 1.0
    assert opex.badge() is None


# -- tier resolution -----------------------------------------------------

def test_current_tier_uses_the_us_date_not_the_local_one(opex_on):
    # 01:30 Berlin on Saturday 22 Aug is still 19:30 Friday 21 Aug in New
    # York -- still monthly opex. A naive date.today() would say Saturday.
    from zoneinfo import ZoneInfo
    berlin_saturday = dt.datetime(2026, 8, 22, 1, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    assert opex.current_tier(berlin_saturday) == opex.MONTHLY


def test_current_tier_classifies_each_day(opex_on):
    assert opex.current_tier(MONTHLY_DAY) == opex.MONTHLY
    assert opex.current_tier(WEEKLY_DAY) == opex.WEEKLY
    assert opex.current_tier(PLAIN_DAY) is None


# -- thresholds ----------------------------------------------------------

def test_monthly_raises_confidence_and_confluence(opex_on):
    assert opex.effective_min_confidence_level(opex.MONTHLY) == 5
    assert opex.effective_min_confluence(2, opex.MONTHLY) == 3


def test_weekly_raises_confluence_only(opex_on):
    assert opex.effective_min_confidence_level(opex.WEEKLY) == 4
    assert opex.effective_min_confluence(2, opex.WEEKLY) == 3


def test_confidence_bump_is_capped_at_five(opex_on, monkeypatch):
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 5)
    assert opex.effective_min_confidence_level(opex.MONTHLY) == 5


def test_confluence_bump_is_capped_at_ten(opex_on):
    assert opex.effective_min_confluence(10, opex.MONTHLY) == 10


# -- the near-close window ----------------------------------------------

@pytest.mark.parametrize("hour,minute,expected", [
    (14, 59, False),   # 61 min out -- outside a 60-minute window
    (15, 0, True),     # exactly 60 min out -- boundary is inclusive
    (15, 30, True),
    (15, 59, True),
    (16, 1, False),    # after the close, nothing left to suppress
])
def test_suppression_window_boundaries(opex_on, hour, minute, expected):
    now = dt.datetime(2026, 8, 21, hour, minute, tzinfo=opex.US_MARKET_TZ)
    assert opex.suppress_new_entries(now) is expected


def test_weekly_never_suppresses(opex_on):
    near_close = dt.datetime(2026, 8, 14, 15, 30, tzinfo=opex.US_MARKET_TZ)
    assert opex.suppress_new_entries(near_close) is False


def test_zero_minutes_disables_the_window(opex_on, monkeypatch):
    monkeypatch.setattr(config, "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES", 0)
    now = dt.datetime(2026, 8, 21, 15, 59, tzinfo=opex.US_MARKET_TZ)
    assert opex.suppress_new_entries(now) is False


# -- multipliers and badge ----------------------------------------------

def test_monthly_multipliers(opex_on):
    assert opex.stop_mult(opex.MONTHLY) == pytest.approx(1.10)
    assert opex.size_mult(opex.MONTHLY) == pytest.approx(0.75)


def test_weekly_leaves_stop_and_size_alone(opex_on):
    assert opex.stop_mult(opex.WEEKLY) == 1.0
    assert opex.size_mult(opex.WEEKLY) == 1.0


def test_badge_present_for_both_tiers(opex_on):
    monthly = opex.badge(opex.MONTHLY)
    weekly = opex.badge(opex.WEEKLY)
    assert monthly is not None and "OPEX" in monthly[0]
    assert weekly is not None
    assert monthly != weekly
    assert opex.badge(None) is None
