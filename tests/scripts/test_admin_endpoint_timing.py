"""scripts/ops/admin_endpoint_timing.py: read-only admin endpoint timing (v205 V205-1)."""
import base64
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import admin_endpoint_timing as timing  # noqa: E402

NAMES = ["dashboard", "dashboard_today", "trades", "trades_open", "live",
         "calendar_month", "calendar_day", "calendar_sparklines"]


class _Response:
    def __init__(self, status=200, body=b"{}", header=None):
        self.status_code = status
        self._body = body
        self.headers = {} if header is None else {"Server-Timing": header}

    def get_data(self):
        return self._body


class _Client:
    """Answers every GET with a fixed response and records what was asked."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, path, headers=None):
        self.calls.append((path, dict(headers or {})))
        return self.response


def test_endpoints_are_the_eight_profiled_paths_in_order():
    paths = timing.endpoints("2026-11", "2026-11-03")
    assert list(paths) == NAMES
    assert paths["dashboard_today"] == "/api/v1/dashboard?mode=today"
    assert paths["trades_open"] == "/api/v1/trades?status=open"
    assert paths["calendar_month"] == "/api/v1/calendar/pnl?month=2026-11"
    assert paths["calendar_day"] == "/api/v1/calendar/pnl/day?date=2026-11-03"
    assert paths["calendar_sparklines"] == "/api/v1/calendar/pnl/day/sparklines?date=2026-11-03"


def test_parse_reads_total_db_and_the_statement_count():
    header = 'total;dur=1234.5, db;dur=12.3;desc="29 statements"'
    assert timing.parse_server_timing(header) == {
        "total": {"dur": 1234.5}, "db": {"dur": 12.3, "statements": 29}}


@pytest.mark.parametrize("header", [None, "", "cdn-cache;desc=HIT", "total;dur=abc",
                                    'db;dur=1.0;desc="many statements"'])
def test_a_missing_foreign_or_malformed_header_parses_to_what_it_can(header):
    parsed = timing.parse_server_timing(header)
    assert "total" not in parsed
    assert parsed.get("db", {}).get("statements") is None


def test_time_endpoints_makes_get_requests_only_and_measures_each_run():
    client = _Client(_Response(body=b"x" * 1400, header='total;dur=5.0, db;dur=1.5;desc="3 statements"'))
    rows = timing.time_endpoints(client, {"Authorization": "Basic abc"},
                                 {"dashboard": "/api/v1/dashboard"}, runs=2)
    assert [(r["name"], r["run"]) for r in rows] == [("dashboard", 1), ("dashboard", 2)]
    assert all(r["status"] == 200 and r["bytes"] == 1400 for r in rows)
    assert all(r["db_ms"] == 1.5 and r["statements"] == 3 and r["ms"] >= 0 for r in rows)
    assert [c[0] for c in client.calls] == ["/api/v1/dashboard"] * 2


def test_without_the_header_the_db_columns_are_none_and_print_a_dash():
    rows = timing.time_endpoints(_Client(_Response()), {}, {"live": "/api/v1/live"}, runs=1)
    assert rows[0]["db_ms"] is None and rows[0]["statements"] is None
    table = timing.format_table(rows)
    assert table.splitlines()[0].startswith("| Endpoint |")
    assert "| live | `/api/v1/live` | 1 | 200 |" in table
    assert table.rstrip().endswith("| - | - |")


def test_main_never_prints_the_password_and_fails_on_a_non_200(monkeypatch, capsys):
    client = _Client(_Response(status=500))
    monkeypatch.setattr(timing, "_client", lambda: client)
    monkeypatch.setenv("ADMIN_USERNAME", "partner")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret-v205")
    code = timing.main(["--month", "2026-11", "--date", "2026-11-03", "--runs", "1"])
    out = capsys.readouterr().out
    token = base64.b64encode(b"partner:s3cret-v205").decode("ascii")
    assert code == 1
    assert "s3cret-v205" not in out and token not in out
    assert client.calls[0][1]["Authorization"] == f"Basic {token}"
    assert len(client.calls) == 8


def test_main_without_credentials_exits_2_without_a_request(monkeypatch, capsys):
    monkeypatch.setattr(timing, "_client", lambda: pytest.fail("no request without credentials"))
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert timing.main([]) == 2
    assert "ADMIN_USERNAME" in capsys.readouterr().err


def test_defaults_are_the_berlin_month_and_date(monkeypatch):
    from datetime import datetime, timezone
    # 23:30 UTC on 31 Oct is 00:30 on 1 Nov in Berlin (CET, after the 25 Oct switch).
    monkeypatch.setattr(timing, "_now", lambda: datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc))
    args = timing._parse(["--runs", "3"])
    assert (args.month, args.date, args.runs) == ("2026-11", "2026-11-01", 3)


def test_run_from_stdin_leaves_sys_path_alone(monkeypatch):
    """`python -` sets __file__ to "<stdin>": no real path, so no repo root to add (and no IndexError)."""
    monkeypatch.setattr(timing, "__file__", "<stdin>", raising=False)
    before = list(sys.path)
    timing._ensure_repo_on_path()
    assert sys.path == before


def test_run_with_no_file_leaves_sys_path_alone(monkeypatch):
    monkeypatch.delattr(timing, "__file__", raising=False)
    before = list(sys.path)
    timing._ensure_repo_on_path()
    assert sys.path == before


def test_parse_reads_app_and_snap_and_ignores_the_cdn_entry():
    header = ('total;dur=1234.6, db;dur=12.3;desc="3 statements", app;dur=1222.3, '
              'snap;desc=hit, cfExtPri')
    assert timing.parse_server_timing(header) == {
        "total": {"dur": 1234.6}, "db": {"dur": 12.3, "statements": 3},
        "app": {"dur": 1222.3}, "snap": {"desc": "hit"}}


@pytest.mark.parametrize("header", ["snap;desc=maybe", "snap", "app;dur=x"])
def test_an_unknown_snap_or_a_malformed_app_is_left_out(header):
    parsed = timing.parse_server_timing(header)
    assert "snap" not in parsed and "app" not in parsed


def test_time_endpoints_rows_carry_app_and_snap():
    client = _Client(_Response(header='total;dur=5.0, db;dur=1.5;desc="3 statements", '
                                      'app;dur=3.5, snap;desc=miss'))
    [row] = timing.time_endpoints(client, {}, {"trades": "/api/v1/trades"}, runs=1)
    assert (row["app_ms"], row["snap"]) == (3.5, "miss")


def test_an_older_server_without_the_entries_gives_none():
    client = _Client(_Response(header='total;dur=5.0, db;dur=1.5;desc="3 statements"'))
    [row] = timing.time_endpoints(client, {}, {"trades": "/api/v1/trades"}, runs=1)
    assert row["app_ms"] is None and row["snap"] is None
