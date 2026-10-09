# tests/scanning/test_outlook_session.py
"""v144: when the outlook runs, which session it targets, how late it may fire,
and when the wrap-up is due -- all in ET off the session calendar."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.scanning import outlook_session as osn

BERLIN = ZoneInfo("Europe/Berlin")
ET = ZoneInfo("America/New_York")
SLOT = dt.time(23, 30)


def _field(key):
    return next(field for field in config.FIELDS if field.key == key)


def test_the_fields_ship_inert_and_live_only():
    enabled, slot = _field("NEXT_SESSION_SCAN_ENABLED"), _field("NEXT_SESSION_SCAN_TIME")
    assert enabled.type == "checkbox" and enabled.default == "false"
    assert slot.default == "23:30"
    assert enabled.search_class == slot.search_class == "live_only"
    assert config.NEXT_SESSION_SCAN_ENABLED is False


@pytest.mark.parametrize("raw,expected", [
    ("23:30", dt.time(23, 30)), ("7:05", dt.time(7, 5)), ("", osn.DEFAULT_SLOT),
    ("23.30", osn.DEFAULT_SLOT), ("25:00", osn.DEFAULT_SLOT), (None, osn.DEFAULT_SLOT),
])
def test_parse_slot(raw, expected):
    assert osn.parse_slot(raw) == expected


@pytest.mark.parametrize("now,expected", [
    (dt.datetime(2026, 10, 11, 23, 30, tzinfo=BERLIN), dt.date(2026, 10, 11)),   # Sunday at the slot
    (dt.datetime(2026, 10, 11, 23, 29, tzinfo=BERLIN), dt.date(2026, 10, 8)),    # Sunday before it: Thursday's
    (dt.datetime(2026, 10, 12, 2, 0, tzinfo=BERLIN), dt.date(2026, 10, 11)),     # Monday small hours: Sunday's
    (dt.datetime(2026, 10, 9, 23, 45, tzinfo=BERLIN), dt.date(2026, 10, 8)),     # Friday never runs
    (dt.datetime(2026, 10, 10, 23, 45, tzinfo=BERLIN), dt.date(2026, 10, 8)),    # Saturday never runs
])
def test_latest_slot_date_is_sunday_to_thursday_only(now, expected):
    assert osn.latest_slot_date(now, SLOT) == expected


@pytest.mark.parametrize("run_date,target", [
    (dt.date(2026, 10, 11), dt.date(2026, 10, 12)),     # Sunday -> Monday
    (dt.date(2026, 10, 15), dt.date(2026, 10, 16)),     # Thursday -> Friday
    (dt.date(2027, 3, 25), None),                       # Thursday before Good Friday
    (dt.date(2026, 11, 25), None),                      # Wednesday before Thanksgiving
    (dt.date(2026, 11, 26), dt.date(2026, 11, 27)),     # Thanksgiving -> the half-day
])
def test_target_session_is_the_next_calendar_day_or_nothing(run_date, target):
    assert osn.target_session(run_date) == target


@pytest.mark.parametrize("run_date,bar", [
    (dt.date(2026, 10, 11), dt.date(2026, 10, 9)),      # Sunday reads Friday's bar
    (dt.date(2026, 10, 12), dt.date(2026, 10, 12)),     # Monday reads Monday's
    (dt.date(2026, 11, 26), dt.date(2026, 11, 25)),     # Thanksgiving reads Wednesday's
])
def test_signal_session_is_the_last_session_on_or_before_the_run_date(run_date, bar):
    assert osn.signal_session(run_date) == bar


def test_a_late_fire_is_allowed_only_before_the_target_sessions_rth_open():
    sunday = dt.date(2026, 10, 11)
    assert osn.fire_allowed(dt.datetime(2026, 10, 12, 15, 29, tzinfo=BERLIN), sunday)
    assert not osn.fire_allowed(dt.datetime(2026, 10, 12, 15, 30, tzinfo=BERLIN), sunday)


def test_the_late_fire_cutoff_follows_et_in_the_dst_mismatch_week():
    sunday = dt.date(2027, 3, 14)                       # Monday 03-15: US on DST, Europe not
    assert osn.fire_allowed(dt.datetime(2027, 3, 15, 14, 29, tzinfo=BERLIN), sunday)
    assert not osn.fire_allowed(dt.datetime(2027, 3, 15, 14, 30, tzinfo=BERLIN), sunday)


def test_the_wrapup_is_due_fifteen_minutes_after_the_official_close():
    monday, half = dt.date(2026, 10, 12), dt.date(2026, 11, 27)
    assert not osn.wrapup_due(dt.datetime(2026, 10, 12, 16, 14, tzinfo=ET), monday)
    assert osn.wrapup_due(dt.datetime(2026, 10, 12, 16, 15, tzinfo=ET), monday)
    assert osn.wrapup_due(dt.datetime(2026, 11, 27, 13, 15, tzinfo=ET), half)


def test_wrapup_candidates_are_the_last_two_sessions():
    assert osn.wrapup_candidates(dt.datetime(2026, 10, 12, 20, 0, tzinfo=ET)) == \
        [dt.date(2026, 10, 9), dt.date(2026, 10, 12)]
    assert osn.wrapup_candidates(dt.datetime(2026, 10, 11, 12, 0, tzinfo=ET)) == \
        [dt.date(2026, 10, 8), dt.date(2026, 10, 9)]
