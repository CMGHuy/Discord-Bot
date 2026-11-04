"""v205 V205-4/V205-4b: the eight profiled endpoints against goldens frozen from pre-v205 code.

V205-4 pins the book and the clock; V205-4b appends the golden and money tests.
Layer 1's refactors (V205-7..V205-10) must pass these unchanged."""
from datetime import date, datetime, timezone

import pytest

from tests.admin_perf import golden_book as gb

NAMES = list(gb.ENDPOINTS)


def _get(client, name):
    response = client.get(gb.ENDPOINTS[name])
    assert response.status_code == 200, (name, response.status_code, response.get_data()[:300])
    return response.get_json()


@pytest.mark.parametrize("name", NAMES)
def test_every_endpoint_answers_on_the_golden_book(name, golden_seed, frozen_clock, logged_in):
    assert _get(logged_in, name) is not None


@pytest.mark.parametrize("name", NAMES)
def test_clock_modules_cover_every_clock_read(name, golden_seed, probe_clock, logged_in):
    gb.CALLERS.clear()                                  # the login above read the clock too
    _get(logged_in, name)
    readers = {caller for caller in gb.CALLERS if caller.startswith("swingbot.")}
    assert readers <= set(gb.CLOCK_MODULES), sorted(readers - set(gb.CLOCK_MODULES))


def test_the_frozen_clock_keeps_isinstance_working():
    assert isinstance(datetime(2026, 1, 1), gb.FrozenDatetime)
    assert isinstance(gb.FrozenDate.today(), date) and gb.FrozenDate.today() == date(2026, 11, 4)
    assert gb.FrozenDatetime.now(timezone.utc) == gb.FROZEN_NOW


def test_the_scale_out_trade_expands_into_two_dated_legs():
    from swingbot.core.tracking.performance import expand_realized_legs
    legs = expand_realized_legs(gb.trades()[3])
    assert [(r["closed_at"], r["realized_pnl_amount"]) for r in legs] == [
        ("2026-10-29T15:00:00+00:00", 50.0), ("2026-11-02T15:00:00+00:00", 20.0)]


def test_mask_and_diff_pointers():
    payload = {"items": [{"id": "x", "amount": 1.0}], "total": 2.0}
    assert gb.mask(payload, ["/items/0/amount"]) == {"items": [{"id": "x", "amount": gb.MASK}], "total": 2.0}
    assert gb.mask(payload) == payload and gb.mask(payload) is not payload
    assert gb.diff_pointers(payload, {"items": [{"id": "x", "amount": 3.0}], "total": 2.0}) == {"/items/0/amount"}
    assert gb.diff_pointers([1], [1, 2]) == {""}
