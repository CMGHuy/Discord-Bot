"""v205 V205-5: what one cold request of each profiled endpoint costs on the golden book.

BUDGETS[name] = (max SQL statements, max Repository.list_all calls), measured on
pre-memo code (V205-5) by test_probe_records_todays_cost and copied in by hand. The
tests assert <=, so a change that makes an endpoint cheaper still passes and one that
makes it dearer fails here rather than on a page. V205-9 lowered the list_all numbers
once @read_scope was on (statements unchanged); nothing else edits BUDGETS.

The comment after each entry is the probe's list_all call list: which stores the
endpoint loaded, and how many times, before v205."""
import json
import os

import pytest

from swingbot.core.db.repositories.base import Repository
from tests.admin_perf import golden_book as gb

NAMES = list(gb.ENDPOINTS)

BUDGETS: dict[str, tuple[int, int]] = {
    "dashboard": (12, 4),  # list_all: TradeRepository x2, PlanRepository x1, JournalRepository x1 (probe, v205 V205-9 scoped)
    "dashboard_today": (12, 4),  # list_all: TradeRepository x2, PlanRepository x1, JournalRepository x1 (probe, v205 V205-9 scoped)
    "trades": (3, 3),  # list_all: PlanRepository x1, TradeRepository x1, JournalRepository x1 (probe, v205 V205-9 scoped)
    "trades_open": (3, 3),  # list_all: PlanRepository x1, TradeRepository x1, JournalRepository x1 (probe, v205 V205-9 scoped)
    "live": (12, 3),  # list_all: PlanRepository x1, TradeRepository x2 (probe, v205 V205-9 scoped)
    "calendar_month": (2, 2),  # list_all: TradeRepository x1, JournalRepository x1 (probe, v205 V205-9 scoped)
    "calendar_day": (2, 2),  # list_all: TradeRepository x1, JournalRepository x1 (probe, v205 V205-9 scoped)
    "calendar_sparklines": (2, 2),  # list_all: TradeRepository x1, JournalRepository x1 (probe, v205 V205-9 scoped)
}


def _cost(client, name, monkeypatch) -> tuple[int, list[str]]:
    """(SQL statements, list_all caller classes) of one GET of ``name``."""
    calls: list[str] = []
    real = Repository.list_all

    def counting(self, *args, **kwargs):
        calls.append(type(self).__name__)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Repository, "list_all", counting)
    try:
        response = client.get(gb.ENDPOINTS[name])
    finally:
        monkeypatch.setattr(Repository, "list_all", real)
    assert response.status_code == 200, (name, response.status_code, response.get_data()[:300])
    timing = gb.admin_endpoint_timing.parse_server_timing(response.headers.get("Server-Timing"))
    assert "db" in timing, f"{name}: no Server-Timing db entry: {response.headers.get('Server-Timing')!r}"
    return int(timing["db"]["statements"]), calls


@pytest.mark.skipif(not os.environ.get("ADMIN_PERF_PROBE"),
                    reason="probe only: ADMIN_PERF_PROBE=<file> appends today's cost per endpoint")
@pytest.mark.parametrize("name", NAMES)
def test_probe_records_todays_cost(name, golden_seed, frozen_clock, sql_counted, logged_in, monkeypatch):
    statements, calls = _cost(logged_in, name, monkeypatch)
    with open(os.environ["ADMIN_PERF_PROBE"], "a", encoding="utf-8") as out:
        out.write(json.dumps({"name": name, "statements": statements,
                              "list_all": len(calls), "calls": calls}) + "\n")


def test_every_endpoint_has_a_budget():
    assert list(BUDGETS) == NAMES
    for name, budget in BUDGETS.items():
        assert len(budget) == 2, name
        statements, list_all = budget
        assert isinstance(statements, int) and statements > 0, name
        assert isinstance(list_all, int) and list_all >= 0, name


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_stays_within_its_budget(name, golden_seed, frozen_clock, sql_counted, logged_in, monkeypatch):
    statements, calls = _cost(logged_in, name, monkeypatch)
    max_statements, max_list_all = BUDGETS[name]
    assert statements <= max_statements, f"{name}: {statements} SQL statements > budget {max_statements}"
    assert len(calls) <= max_list_all, f"{name}: list_all x{len(calls)} > budget {max_list_all}: {calls}"


def test_the_counters_see_a_request(golden_seed, frozen_clock, sql_counted, logged_in, monkeypatch):
    statements, calls = _cost(logged_in, "dashboard", monkeypatch)
    assert statements > 0
    assert "TradeRepository" in calls and "PlanRepository" in calls, calls
