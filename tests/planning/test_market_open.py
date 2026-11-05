"""V192-8: which NYSE session's open decides a waiting market plan, and where a
poll sits against it. Pure: no store, no price."""
import datetime as dt

import pytest

from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning import market_open as mo
from swingbot.core.planning.plan_types import PlanStatus
from tests.planning.test_plan_engine_model import _plan


def _et(month, day, hh, mm=0):
    return dt.datetime(2026, month, day, hh, mm, tzinfo=US_MARKET_TZ)


def _waiting(**kw):
    base = dict(source="confluence", strategy="S/R Confluence", created_at="2026-10-13",
                issued_at=_et(10, 13, 15).isoformat(), status=PlanStatus.PENDING,
                waits_next_open=True, stop_loss=98.5, tp1=103.0)
    base.update(kw)
    return _plan(**base)


def test_the_premarket_confirm_count_is_two():
    assert mo.PREMARKET_STOP_CONFIRM_POLLS == 2


def test_the_phase_names_are_the_frozen_strings():
    assert (mo.BEFORE, mo.EXTENDED, mo.OPEN, mo.MISSED, mo.WAITING, mo.AFTER_CLOSE) == (
        "before", "extended", "open", "missed", "waiting", "after_close")


@pytest.mark.parametrize("issued, expected", [
    (_et(10, 13, 15), dt.date(2026, 10, 14)),         # after Tuesday's open -> Wednesday
    (_et(10, 13, 8), dt.date(2026, 10, 13)),          # Tuesday premarket -> Tuesday's open
    (_et(10, 13, 9, 30), dt.date(2026, 10, 13)),      # exactly at the open: that open
    (_et(10, 13, 9, 31), dt.date(2026, 10, 14)),
    (_et(10, 16, 17), dt.date(2026, 10, 19)),         # Friday evening -> Monday
    (_et(10, 17, 10), dt.date(2026, 10, 19)),         # Saturday -> Monday
    (_et(11, 26, 12), dt.date(2026, 11, 27)),         # Thanksgiving -> the half-day after
])
def test_deciding_session_from_issued_at(issued, expected):
    assert mo.deciding_session(_waiting(issued_at=issued.isoformat())) == expected


def test_issued_at_is_read_in_et_and_naive_means_utc():
    # 13:00 UTC = 09:00 ET: before Tuesday's open
    assert mo.deciding_session(_waiting(issued_at="2026-10-13T13:00:00+00:00")) == dt.date(2026, 10, 13)
    # naive 14:00 is UTC = 10:00 ET: after the open
    assert mo.deciding_session(_waiting(issued_at="2026-10-13T14:00:00")) == dt.date(2026, 10, 14)


@pytest.mark.parametrize("created, expected", [
    ("2026-10-13", dt.date(2026, 10, 14)),
    ("2026-10-16", dt.date(2026, 10, 19)),
    ("2026-10-13T00:00:00+00:00", dt.date(2026, 10, 14)),   # UTC midnight = that date
    ("2026-10-13T20:30:00-04:00", dt.date(2026, 10, 14)),   # its ET date
])
def test_without_issued_at_the_session_after_created_at_decides(created, expected):
    assert mo.deciding_session(_waiting(issued_at=None, created_at=created)) == expected


def test_an_unreadable_issued_at_falls_back_and_unreadable_both_give_none():
    assert mo.deciding_session(_waiting(issued_at="garbage")) == dt.date(2026, 10, 14)
    assert mo.deciding_session(_waiting(issued_at="garbage", created_at="nope")) is None


@pytest.mark.parametrize("now, phase", [
    (_et(10, 13, 15, 30), mo.BEFORE),      # the alert day's RTH, after the issue
    (_et(10, 13, 16, 30), mo.EXTENDED),    # the alert day's after-hours tape
    (_et(10, 14, 2, 30), mo.BEFORE),       # polled, but before any tape exists
    (_et(10, 14, 8, 0), mo.EXTENDED),      # the deciding day's premarket
    (_et(10, 14, 9, 30), mo.OPEN),
    (_et(10, 14, 15, 59), mo.OPEN),        # the first RTH poll decides, whenever it lands
    (_et(10, 14, 16, 30), mo.MISSED),      # the deciding close passed with no RTH poll
    (_et(10, 15, 8, 0), mo.MISSED),
    (_et(10, 15, 10, 0), mo.MISSED),
])
def test_market_phase(now, phase):
    assert mo.market_phase(_waiting(), now) == phase


def test_a_half_day_deciding_session_is_missed_after_its_13_00_close():
    plan = _waiting(issued_at=_et(11, 26, 12).isoformat(), created_at="2026-11-26")
    assert mo.market_phase(plan, _et(11, 27, 12, 59)) == mo.OPEN
    assert mo.market_phase(plan, _et(11, 27, 13, 30)) == mo.MISSED


def test_no_deciding_session_is_missed():
    assert mo.market_phase(_waiting(issued_at="x", created_at="y"), _et(10, 14, 10)) == mo.MISSED


@pytest.mark.parametrize("now, phase", [
    (_et(10, 14, 11), mo.WAITING),
    (_et(10, 14, 15, 59), mo.WAITING),
    (_et(10, 14, 16, 0), mo.AFTER_CLOSE),     # the close is exclusive
    (_et(10, 15, 9, 45), mo.AFTER_CLOSE),     # the bot was down across the close
])
def test_a_plan_resting_for_its_reclaim(now, phase):
    assert mo.market_phase(_waiting(reclaim_session="2026-10-14"), now) == phase
