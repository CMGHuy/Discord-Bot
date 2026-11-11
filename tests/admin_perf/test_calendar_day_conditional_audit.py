"""v218 V218-12: /calendar/pnl/day audited for the conditional allow-list -- dropped (v206 P3-c).

The day body's `as_of` is stamped per request (api_v1/calendar.py:157), and its
FX `fetch` flag follows the refresher (api_v1/money.py:23-25). The sparklines
route also stamps `as_of` (calendar.py:202) and reads daily frames that no tag
input versions (calendar.py:198-199): it stays off without a key audit.
Recorded in v206 `### Plan 3 route audits (V218-10..12)`; the allow-list itself
is pinned by tests/admin_perf/test_conditional_routes.py (V218-13)."""
import datetime as dt

import pytest

from swingbot.admin.api_v1 import conditional as cond
from tests.admin_perf import golden_book as gb

NOON = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)
ROUTES = {"calendar_day": "api_v1.calendar_pnl_day",
          "calendar_sparklines": "api_v1.calendar_pnl_day_sparklines"}


def _get(client, name: str) -> dict:
    response = client.get(gb.ENDPOINTS[name])
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


@pytest.mark.parametrize("name", list(ROUTES))
def test_as_of_moves_within_one_berlin_day_on_an_unchanged_book(name, golden_seed, frozen_clock,
                                                                logged_in, monkeypatch):
    monkeypatch.setattr(gb, "FROZEN_NOW", NOON)
    first = _get(logged_in, name)
    monkeypatch.setattr(gb, "FROZEN_NOW", NOON + dt.timedelta(minutes=5))
    second = _get(logged_in, name)
    assert first["as_of"] != second["as_of"]
    assert gb.diff_pointers(first, second) == {"/as_of"}     # nothing about the book moved


def test_the_day_converts_with_a_fetch_flag_that_follows_the_refresher(admin_app, monkeypatch):
    from swingbot import config
    from swingbot.admin.api_v1 import money
    seen = []
    monkeypatch.setattr(money.fx_convert, "to_account_currency",
                        lambda rows, *, account=None, fetch: seen.append(fetch) or rows)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    for refresher in ("off", "on"):
        monkeypatch.setattr(config, "ADMIN_REFRESHER", refresher)
        money.to_account_currency([])
    assert seen == [True, False]


@pytest.mark.parametrize("name", list(ROUTES))
def test_the_day_views_are_not_conditional(name, admin_app):
    assert not hasattr(admin_app.view_functions[ROUTES[name]], cond.CONDITIONAL_ATTR)


@pytest.mark.parametrize("name", list(ROUTES))
def test_the_day_views_keep_no_store(name, golden_seed, frozen_clock, logged_in):
    response = logged_in.get(gb.ENDPOINTS[name])
    assert response.status_code == 200
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"
