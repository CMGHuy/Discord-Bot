"""v205 V205-4/V205-4b: the eight profiled endpoints against goldens frozen from pre-v205 code.

V205-4 pins the book and the clock; V205-4b appends the golden and money tests.
Layer 1's refactors (V205-7..V205-10) must pass these unchanged."""
import json
import os
from datetime import date, datetime, timezone

import pytest

from tests.admin_perf import golden_book as gb
from tests.admin_perf import money_reference as mr
from tests.admin_perf import record_golden

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


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_matches_its_frozen_golden(name, golden_seed, frozen_clock, logged_in):
    live = _get(logged_in, name)
    if os.environ.get("ADMIN_PERF_RECORD") == "1":
        record_golden.write_golden(name, live)
    golden = json.loads(gb.golden_path(name).read_text(encoding="utf-8"))
    pointers = list(mr.EXPECTED_MONEY[name])
    assert gb.mask(gb.without_added(name, live), pointers) == gb.mask(golden, pointers)


@pytest.mark.parametrize("name", NAMES)
def test_money_fields_match_the_hand_computed_reference(name, golden_seed, frozen_clock, logged_in):
    live = _get(logged_in, name)
    for pointer, expected in mr.EXPECTED_MONEY[name].items():
        actual = gb.resolve(live, pointer)
        if isinstance(expected, float):
            assert actual == pytest.approx(expected, abs=0.005), pointer
        else:
            assert actual == expected, pointer


@pytest.mark.parametrize("name", NAMES)
def test_money_pointers_are_exactly_the_fx_sensitive_fields(name, golden_seed, frozen_clock, logged_in):
    base = _get(logged_in, name)
    golden_seed.set_fx(2.0)                             # every USDEUR=X close doubled
    doubled = _get(logged_in, name)
    assert gb.diff_pointers(gb.mask(gb.without_added(name, base)),
                            gb.mask(gb.without_added(name, doubled))) == set(mr.EXPECTED_MONEY[name])


def test_without_added_drops_only_the_listed_pointers():
    live = {"market_meta": {"a": 1}, "equity_30d": {"points": [], "market_meta": {"b": 2}}}
    assert gb.without_added("dashboard", live) == {"market_meta": {"a": 1}, "equity_30d": {"points": []}}
    assert gb.without_added("calendar_month", {"market_meta": 1, "x": 2}) == {"x": 2}
    assert gb.without_added("trades", live) == live
    assert gb.without_added("dashboard", {}) == {}
    assert "market_meta" in live["equity_30d"]               # the caller's payload is untouched


def test_no_golden_is_ever_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(gb, "GOLDEN_DIR", tmp_path)
    assert record_golden.write_golden("dashboard", {"a": 1}) is True
    assert record_golden.write_golden("dashboard", {"a": 2}) is False
    assert json.loads((tmp_path / "dashboard.json").read_text(encoding="utf-8")) == {"a": 1}
