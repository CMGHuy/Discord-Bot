"""v218 V218-5: the eight goldens are byte-identical with the snapshot on, cold and
warm, and with the switch off; a warm request loads fewer stores than v205's budget.
Goldens are never regenerated (golden_book.py)."""
import json

import pytest

from swingbot import config
from tests.admin_perf import golden_book as gb
from tests.admin_perf import money_reference as mr
from tests.admin_perf.test_budgets import BUDGETS, _cost

NAMES = list(gb.ENDPOINTS)


def _matches_golden(name, live) -> bool:
    golden = json.loads(gb.golden_path(name).read_text(encoding="utf-8"))
    pointers = list(mr.EXPECTED_MONEY[name])
    return gb.mask(gb.without_added(name, live), pointers) == gb.mask(golden, pointers)


def _get(client, name):
    response = client.get(gb.ENDPOINTS[name])
    assert response.status_code == 200, (name, response.status_code, response.get_data()[:300])
    return response.get_json()


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_matches_its_frozen_golden_on_the_snapshot(name, golden_seed, frozen_clock,
                                                            logged_in, snapshot_on):
    assert _matches_golden(name, _get(logged_in, name)), f"{name}: cold"
    assert _matches_golden(name, _get(logged_in, name)), f"{name}: warm"
    assert any(snapshot_on.stored(key) is not None for key in snapshot_on.SNAPSHOT_KEYS)


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_matches_its_frozen_golden_with_the_switch_off(name, golden_seed, frozen_clock,
                                                                logged_in, snapshot_on, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "off")
    assert _matches_golden(name, _get(logged_in, name))
    assert all(snapshot_on.stored(key) is None for key in snapshot_on.SNAPSHOT_KEYS)


@pytest.mark.parametrize("name", NAMES)
def test_a_warm_request_loads_fewer_stores_than_the_budget(name, golden_seed, frozen_clock, sql_counted,
                                                           logged_in, snapshot_on, monkeypatch):
    _cost(logged_in, name, monkeypatch)                     # cold: fills the snapshot
    _statements, calls = _cost(logged_in, name, monkeypatch)
    assert len(calls) < BUDGETS[name][1], f"{name}: warm list_all {calls}"


def test_a_warm_trades_page_loads_no_trades_or_plans(golden_seed, frozen_clock, sql_counted,
                                                     logged_in, snapshot_on, monkeypatch):
    _cost(logged_in, "trades", monkeypatch)
    _statements, calls = _cost(logged_in, "trades", monkeypatch)
    assert "TradeRepository" not in calls and "PlanRepository" not in calls, calls
