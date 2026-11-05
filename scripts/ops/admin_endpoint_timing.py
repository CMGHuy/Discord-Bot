"""Read-only timing of the admin's eight profiled endpoints (v205 V205-1).

Runs INSIDE the admin container, against the app in-process through Flask's
test client, so the number is the server's own work with no network or
gunicorn queueing in it:

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin \
        python - --month 2026-11 --date 2026-11-03 --runs 2" < scripts/ops/admin_endpoint_timing.py

(once deployed: ``docker compose exec -T admin python scripts/ops/admin_endpoint_timing.py``).

GET requests only, authenticated with HTTP Basic from the container's own
ADMIN_USERNAME/ADMIN_PASSWORD; neither is ever printed. Importing
swingbot.admin.app starts no thread (the SSE listener starts on the first
subscriber), and a GET does exactly what a browser's page load does.

The db columns come from the ``Server-Timing`` header v205 adds (V205-3):
``total;dur=<ms>, db;dur=<ms>;desc="<n> statements"``. Before that ships
they print ``-``.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
_HEADER = "| Endpoint | Path | Run | Status | ms | Bytes | db ms | Statements |"
_RULE = "|---|---|---|---|---|---|---|---|"


def endpoints(month: str, day: str) -> dict[str, str]:
    """Endpoint name -> path. These names are the ones every v205 task uses."""
    return {
        "dashboard": "/api/v1/dashboard",
        "dashboard_today": "/api/v1/dashboard?mode=today",
        "trades": "/api/v1/trades",
        "trades_open": "/api/v1/trades?status=open",
        "live": "/api/v1/live",
        "calendar_month": f"/api/v1/calendar/pnl?month={month}",
        "calendar_day": f"/api/v1/calendar/pnl/day?date={day}",
        "calendar_sparklines": f"/api/v1/calendar/pnl/day/sparklines?date={day}",
    }


def _metric(params: list[str]) -> dict:
    """``dur=<float>`` and ``desc="<n> statements"`` of one header entry."""
    entry: dict = {}
    for param in params:
        key, _, value = param.partition("=")
        try:
            if key == "dur":
                entry["dur"] = float(value)
            elif key == "desc":
                entry["statements"] = int(value.strip('"').split(" ")[0])
        except ValueError:
            continue
    return entry


def parse_server_timing(header: str | None) -> dict[str, dict]:
    """``{"total": {"dur"}, "db": {"dur", "statements"}}``; whatever is unreadable is left out."""
    parsed: dict[str, dict] = {}
    for part in (header or "").split(","):
        bits = [bit.strip() for bit in part.split(";")]
        if bits[0] in ("total", "db"):
            entry = _metric(bits[1:])
            if "dur" in entry:
                parsed[bits[0]] = entry
    return parsed


def time_endpoints(client, headers: dict, paths: dict[str, str], *, runs: int = 2) -> list[dict]:
    """Every path ``runs`` times, in order: wall ms, status, bytes, db ms, statements."""
    rows = []
    for run in range(1, runs + 1):
        for name, path in paths.items():
            started = time.perf_counter()
            response = client.get(path, headers=headers)
            elapsed_ms = (time.perf_counter() - started) * 1000
            db = parse_server_timing(response.headers.get("Server-Timing")).get("db", {})
            rows.append({"name": name, "path": path, "run": run,
                         "status": response.status_code, "ms": round(elapsed_ms, 1),
                         "bytes": len(response.get_data()),
                         "db_ms": db.get("dur"), "statements": db.get("statements")})
    return rows


def _cell(value) -> str:
    return "-" if value is None else str(value)


def format_table(rows: list[dict]) -> str:
    lines = [_HEADER, _RULE]
    for r in rows:
        lines.append(f"| {r['name']} | `{r['path']}` | {r['run']} | {r['status']} | {r['ms']} "
                     f"| {r['bytes']} | {_cell(r['db_ms'])} | {_cell(r['statements'])} |")
    return "\n".join(lines) + "\n"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(argv: list[str] | None) -> argparse.Namespace:
    berlin = _now().astimezone(BERLIN)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--month", default=berlin.strftime("%Y-%m"), help="YYYY-MM (default: Berlin month)")
    parser.add_argument("--date", default=berlin.date().isoformat(), help="YYYY-MM-DD (default: Berlin date)")
    parser.add_argument("--runs", type=int, default=2)
    return parser.parse_args(argv)


def _ensure_repo_on_path() -> None:
    """``python scripts/ops/x.py`` puts scripts/ops on sys.path, not the repo root.

    Under ``python -`` (stdin, as in the admin container) ``__file__`` is "<stdin>", not a
    file: there is no checkout to add, and the app root is already importable.
    """
    here = globals().get("__file__")
    if here and Path(here).is_file():
        root = str(Path(here).resolve().parents[2])
        if root not in sys.path:
            sys.path.insert(0, root)


def _client():
    _ensure_repo_on_path()
    from swingbot.admin.app import app
    return app.test_client()


def _auth_headers(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    username, password = os.environ.get("ADMIN_USERNAME"), os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        print("ADMIN_USERNAME/ADMIN_PASSWORD are not set in this environment", file=sys.stderr)
        return 2
    rows = time_endpoints(_client(), _auth_headers(username, password),
                          endpoints(args.month, args.date), runs=args.runs)
    print(format_table(rows), end="")
    return 0 if all(r["status"] == 200 for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
