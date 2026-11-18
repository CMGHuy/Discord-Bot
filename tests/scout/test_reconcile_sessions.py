"""v232: UTC stamps to NYSE sessions, issue-time buckets, stamp sources."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
import reconcile  # noqa: E402
from reconcile import sessions  # noqa: E402

D = dt.date


def test_the_package_names_its_git_ignored_work_dir():
    assert reconcile.WORK_DIR == Path("data/v232")
    assert "live_replay_reconcile.py" in reconcile.__doc__


@pytest.mark.parametrize("text", ["2026-09-15T08:54:50Z", "2026-09-15T08:54:50+00:00",
                                  "2026-09-15 08:54:50+00", "2026-09-15T04:54:50-04:00",
                                  "2026-09-15T08:54:50"])
def test_to_utc_reads_every_stored_form(text):
    assert sessions.to_utc(text) == dt.datetime(2026, 9, 15, 8, 54, 50, tzinfo=dt.timezone.utc)


def test_to_utc_keeps_microseconds_and_converts_aware_datetimes():
    got = sessions.to_utc("2026-03-02T14:35:10.123456+00:00")
    assert got.microsecond == 123456
    et = dt.datetime(2026, 11, 2, 9, 31, tzinfo=sessions.session.US_MARKET_TZ)
    assert sessions.to_utc(et) == dt.datetime(2026, 11, 2, 14, 31, tzinfo=dt.timezone.utc)


def test_to_utc_refuses_a_bare_date():
    with pytest.raises(ValueError, match="date"):
        sessions.to_utc("2026-09-15")


def test_ny_time_follows_the_clock_change():
    assert sessions.ny_time("2026-10-30T13:31:00Z").strftime("%H:%M %Z") == "09:31 EDT"
    assert sessions.ny_time("2026-11-02T13:31:00Z").strftime("%H:%M %Z") == "08:31 EST"


@pytest.mark.parametrize("stamp, session_day", [
    ("2026-10-30T13:31:00Z", D(2026, 10, 30)),   # 09:31 EDT: after the open
    ("2026-11-02T13:31:00Z", D(2026, 10, 30)),   # 08:31 EST: pre-open -> previous session
    ("2026-11-02T14:29:59Z", D(2026, 10, 30)),   # 09:29:59 EST
    ("2026-11-02T14:30:00Z", D(2026, 11, 2)),    # 09:30 EST exactly: the open
    ("2026-10-31T15:00:00Z", D(2026, 10, 30)),   # Saturday
    ("2026-11-01T18:00:00Z", D(2026, 10, 30)),   # Sunday, the clock-change day
    ("2026-11-10T22:00:00Z", D(2026, 11, 10)),   # 17:00 EST: after the close
    ("2026-11-11T02:00:00Z", D(2026, 11, 10)),   # 21:00 EST the evening before, UTC next day
    ("2026-11-26T16:00:00Z", D(2026, 11, 25)),   # Thanksgiving
    ("2026-11-27T19:00:00Z", D(2026, 11, 27)),   # 14:00 EST, after the 13:00 early close
])
def test_issue_session(stamp, session_day):
    assert sessions.issue_session(stamp) == session_day


@pytest.mark.parametrize("stamp, inside", [
    ("2026-11-10T14:30:00Z", True), ("2026-11-10T20:59:59Z", True),
    ("2026-11-10T21:00:00Z", False), ("2026-11-10T14:29:00Z", False),
    ("2026-11-27T17:59:00Z", True), ("2026-11-27T18:00:00Z", False),
    ("2026-11-26T16:00:00Z", False), ("2026-10-31T15:00:00Z", False),
])
def test_in_regular_session(stamp, inside):
    assert sessions.in_regular_session(stamp) is inside


def test_minutes_after_open_on_both_sides_of_the_clock_change():
    assert sessions.minutes_after_open("2026-10-30T13:45:00Z") == 15.0   # 09:45 EDT
    assert sessions.minutes_after_open("2026-11-10T14:45:00Z") == 15.0   # 09:45 EST
    assert sessions.minutes_after_open("2026-11-10T14:29:00Z") is None
    assert sessions.minutes_after_open("2026-11-26T16:00:00Z") is None


@pytest.mark.parametrize("stamp, bucket", [
    ("2026-11-10T14:30:00Z", "open_to_1030"), ("2026-11-10T15:29:59Z", "open_to_1030"),
    ("2026-11-10T15:30:00Z", "mid_day"), ("2026-11-10T19:59:59Z", "mid_day"),
    ("2026-11-10T20:00:00Z", "last_hour"), ("2026-11-10T20:59:59Z", "last_hour"),
    ("2026-11-10T21:00:00Z", "outside_session"), ("2026-11-10T12:00:00Z", "outside_session"),
    ("2026-11-27T16:59:00Z", "mid_day"), ("2026-11-27T17:00:00Z", "last_hour"),
    ("2026-10-31T15:00:00Z", "outside_session"),
])
def test_issue_bucket(stamp, bucket):
    assert sessions.issue_bucket(stamp) == bucket
    assert bucket in sessions.ISSUE_BUCKETS


def test_issue_buckets_are_frozen():
    assert sessions.ISSUE_BUCKETS == ("open_to_1030", "mid_day", "last_hour", "outside_session")


def test_stamp_source_prefers_issued_at():
    doc = {"plan_id": "P1", "created_at": "2026-11-09",
           "issued_at": "2026-11-10T15:00:00.500000+00:00"}
    stamp, source = sessions.stamp_source(doc)
    assert source == "issued_at"
    assert stamp == dt.datetime(2026, 11, 10, 15, 0, 0, 500000, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize("doc", [{"plan_id": "P1", "created_at": "2026-11-10"},
                                 {"plan_id": "P1", "created_at": "2026-11-10",
                                  "issued_at": None},
                                 {"plan_id": "P1", "created_at": "2026-11-10",
                                  "issued_at": ""}])
def test_stamp_source_falls_back_to_the_created_bar_close(doc):
    stamp, source = sessions.stamp_source(doc)
    assert source == "created_at"
    assert stamp == dt.datetime(2026, 11, 10, 21, 0, tzinfo=dt.timezone.utc)   # 16:00 EST
    assert sessions.issue_session(stamp) == D(2026, 11, 10)
    assert sessions.issue_bucket(stamp) == "outside_session"


def test_a_created_at_on_an_early_close_maps_to_13_00():
    stamp, _ = sessions.stamp_source({"plan_id": "P1", "created_at": "2026-11-27"})
    assert sessions.ny_time(stamp).strftime("%H:%M") == "13:00"
    assert sessions.issue_session(stamp) == D(2026, 11, 27)


def test_stamp_source_without_any_stamp_is_refused():
    with pytest.raises(ValueError, match="P9"):
        sessions.stamp_source({"plan_id": "P9"})


@pytest.mark.parametrize("a, b, apart", [
    (D(2026, 10, 30), D(2026, 11, 2), 1),      # over a weekend
    (D(2026, 11, 25), D(2026, 11, 27), 1),     # over Thanksgiving
    (D(2026, 11, 2), D(2026, 10, 30), -1),
    (D(2026, 11, 10), D(2026, 11, 10), 0),
    (D(2026, 11, 9), D(2026, 11, 13), 4),
])
def test_sessions_apart(a, b, apart):
    assert sessions.sessions_apart(a, b) == apart
