"""v218 V218-11: /calendar/pnl audited for the conditional allow-list -- dropped (v206 P3-c).

The month body's `as_of` is the time the view was composed
(core/analytics/page_bodies.py:352-354): two requests five minutes apart on an
unchanged book differ, and no ETag input covers a value below day resolution.
`market_meta` follows the refresher (api_v1/analytics.py:132-165) and the
default month is the process-local date (api_v1/calendar.py:62). Recorded in
v206 `### Plan 3 route audits (V218-10..12)`; the allow-list itself is pinned by
tests/admin_perf/test_conditional_routes.py (V218-13)."""
import datetime as dt

from swingbot.admin.api_v1 import conditional as cond
from tests.admin_perf import golden_book as gb

MONTH = gb.ENDPOINTS["calendar_month"]
NOON = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)
REFRESHER_META = {"refreshing", "computed_at", "stale_inputs", "error", "source"}


def _month(client) -> dict:
    response = client.get(MONTH)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_as_of_moves_within_one_berlin_day_on_an_unchanged_book(golden_seed, frozen_clock, logged_in,
                                                                monkeypatch):
    monkeypatch.setattr(gb, "FROZEN_NOW", NOON)
    first = _month(logged_in)
    monkeypatch.setattr(gb, "FROZEN_NOW", NOON + dt.timedelta(minutes=5))
    second = _month(logged_in)
    assert first["as_of"] != second["as_of"]
    assert "/as_of" in gb.diff_pointers(first, second)
    # The book did not change: the month's own numbers are identical.
    assert (first["days"], first["totals"]) == (second["days"], second["totals"])


def test_market_meta_carries_the_refresher_fields(golden_seed, frozen_clock, logged_in):
    assert REFRESHER_META <= set(_month(logged_in)["market_meta"])


def test_the_month_view_is_not_conditional(admin_app):
    view = admin_app.view_functions["api_v1.calendar_pnl"]
    assert not hasattr(view, cond.CONDITIONAL_ATTR)


def test_the_month_view_keeps_no_store(golden_seed, frozen_clock, logged_in):
    response = logged_in.get(MONTH)
    assert response.status_code == 200
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"
