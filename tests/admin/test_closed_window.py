"""v181 -- the `[from, to)` closed-trade window.

One definition, shared by `GET /dashboard?mode=range` and the Closed tab's
`GET /trades?closed_from=&closed_to=`, so the KPIs and the table under them
cannot disagree about which closes a window holds (spec v181 § 6).
"""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot.admin.api_v1 import ApiError
from swingbot.admin.api_v1.closed_window import (
    ClosedWindow,
    closed_in_window,
    parse_closed_window,
)

UTC = timezone.utc
START = datetime(2026, 10, 1, 4, 0, tzinfo=UTC)   # 00:00 New York, 1 Oct
END = datetime(2026, 10, 2, 4, 0, tzinfo=UTC)
WINDOW = ClosedWindow(START, END)


def test_parses_two_aware_bounds_in_any_offset():
    window = parse_closed_window("2026-10-01T04:00:00+00:00", "2026-10-02T00:00:00-04:00")
    assert window == WINDOW


def test_accepts_the_form_the_spa_sends():
    # Date.toISOString() -> milliseconds and a Z suffix.
    assert parse_closed_window("2026-10-01T04:00:00.000Z", "2026-10-02T04:00:00.000Z") == WINDOW


def test_an_empty_window_is_allowed():
    assert parse_closed_window(START.isoformat(), START.isoformat()) == ClosedWindow(START, START)


@pytest.mark.parametrize("from_raw, to_raw, names_in_message", [
    (None, "2026-10-02T04:00:00+00:00", "from"),
    ("2026-10-01T04:00:00+00:00", "", "to"),
    ("2026-10-01T04:00:00", "2026-10-02T04:00:00+00:00", "timezone"),
    ("2026-10-01", "2026-10-02T04:00:00+00:00", "timezone"),
    ("yesterday", "2026-10-02T04:00:00+00:00", "from"),
    ("2026-10-02T04:00:00+00:00", "2026-10-01T04:00:00+00:00", "after"),
])
def test_rejects_a_bad_window_with_a_400(from_raw, to_raw, names_in_message):
    with pytest.raises(ApiError) as caught:
        parse_closed_window(from_raw, to_raw)
    assert (caught.value.code, caught.value.status) == ("invalid", 400)
    assert names_in_message in caught.value.message


def test_names_the_parameters_it_was_given():
    with pytest.raises(ApiError) as caught:
        parse_closed_window(None, END.isoformat(), names=("closed_from", "closed_to"))
    assert "closed_from" in caught.value.message


def test_a_close_at_from_counts_and_one_at_to_does_not():
    assert closed_in_window(START.isoformat(), WINDOW)
    assert closed_in_window((END - timedelta(microseconds=1)).isoformat(), WINDOW)
    assert not closed_in_window(END.isoformat(), WINDOW)
    assert not closed_in_window((START - timedelta(seconds=1)).isoformat(), WINDOW)


def test_compares_instants_not_wall_clocks():
    # 00:30 in New York on 1 Oct is 04:30Z: inside, whatever the offset says.
    assert closed_in_window("2026-10-01T00:30:00-04:00", WINDOW)
    assert not closed_in_window("2026-10-01T23:59:00-05:00", WINDOW)


def test_reads_a_naive_stored_close_as_utc():
    # Older records carry naive timestamps; `is_today_berlin` reads them as UTC too.
    assert closed_in_window("2026-10-01T04:00:00", WINDOW)
    assert not closed_in_window("2026-10-01T03:59:59", WINDOW)


@pytest.mark.parametrize("raw", [None, "", "not-a-date"])
def test_a_missing_or_unreadable_close_is_outside(raw):
    assert not closed_in_window(raw, WINDOW)
