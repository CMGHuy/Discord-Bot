"""v217 V217-3: the wider-scope /dashboard `today` block on the golden book.

A `mode=all` request now also computes today's realised figures and lifecycle
counts, from the same loaded trades. These tests prove it costs no more SQL
than the frozen `dashboard` budget, reads the trade log once, equals what
`mode=today` answers, and never appears on the two frozen dashboard goldens."""
import json

from swingbot.core.db.repositories.base import Repository
from tests.admin_perf import golden_book as gb
from tests.admin_perf.test_budgets import BUDGETS

ALL = "/api/v1/dashboard?mode=all"
TODAY = "/api/v1/dashboard?mode=today"


def _cost(client, path, monkeypatch) -> tuple[int, list[str]]:
    """(SQL statements, list_all caller classes) of one GET of ``path``,
    the way test_budgets._cost measures a named endpoint."""
    calls: list[str] = []
    real = Repository.list_all

    def counting(self, *args, **kwargs):
        calls.append(type(self).__name__)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Repository, "list_all", counting)
    try:
        response = client.get(path)
    finally:
        monkeypatch.setattr(Repository, "list_all", real)
    assert response.status_code == 200, (path, response.status_code, response.get_data()[:300])
    assert "today" in response.get_json()
    timing = gb.admin_endpoint_timing.parse_server_timing(response.headers.get("Server-Timing"))
    assert "db" in timing, f"{path}: no Server-Timing db entry"
    return int(timing["db"]["statements"]), calls


def test_mode_all_with_the_block_stays_within_the_dashboard_budget(
        golden_seed, frozen_clock, sql_counted, logged_in, monkeypatch):
    statements, calls = _cost(logged_in, ALL, monkeypatch)
    max_statements, max_list_all = BUDGETS["dashboard"]
    assert statements <= max_statements, f"{statements} SQL statements > budget {max_statements}"
    assert len(calls) <= max_list_all, f"list_all x{len(calls)} > budget {max_list_all}: {calls}"


def test_mode_all_reads_the_trade_log_once(golden_seed, frozen_clock, logged_in, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog

    calls = []
    original = TradeLog.get_trades

    def counting(self, *args, **kwargs):
        calls.append(kwargs.get("status"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TradeLog, "get_trades", counting)
    assert logged_in.get(ALL).status_code == 200
    assert len(calls) == 1, f"get_trades called {len(calls)} times: {calls}"


def test_the_block_equals_mode_today_on_the_golden_book(golden_seed, frozen_clock, logged_in):
    """FROZEN_NOW is 2026-11-04 12:00 UTC and the book's last close is
    2026-11-03 20:30 UTC (21:30 Berlin), so today is a measured zero."""
    block = logged_in.get(ALL).get_json()["today"]
    today = logged_in.get(TODAY).get_json()
    assert block == {"realized": today["realized"], "lifecycle": today["lifecycle"]}
    assert block["realized"]["n"] == 0
    assert block["realized"]["amount"] is None


def test_the_frozen_dashboard_goldens_carry_no_block(golden_seed, frozen_clock, logged_in):
    for name in ("dashboard", "dashboard_today"):
        assert "today" not in logged_in.get(gb.ENDPOINTS[name]).get_json(), name
        assert "today" not in json.loads(gb.golden_path(name).read_text(encoding="utf-8")), name
