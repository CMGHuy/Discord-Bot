"""Shadow soak verdict from scan telemetry (v245, spec § Switch criteria).

Usage:
    python scripts/perf/analysis_cache_soak_report.py [--since ISO | --since-deploy] [--first-full-day YYYY-MM-DD] [--need 5] [--path FILE]

On production, read-only, piped to the bot container (working directory /app):
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since-deploy" < scripts/perf/analysis_cache_soak_report.py

Reads only rows written in ANALYSIS_CACHE=shadow (cache_mode "shadow" with
integer cache_compared / cache_diffs), groups them by New York date and prints
one JSON object. Verdict: FAIL on any diff; PASS once `need` trading days
(weekday, not an NYSE holiday, session over, at least one compared ticker)
have zero diffs; WAIT otherwise. If shadow started during a session, set
--first-full-day to the first eligible New York trading date. Earlier rows
within the telemetry window still fail the soak if they contain a diff.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from scripts.perf.analysis_phase_report import _read, _when, last_deploy_at

try:  # the NYSE calendar; importable from the repo root and in the bot container
    from swingbot.core.market.session import NYSE_HOLIDAYS as _HOLIDAYS
except ImportError:  # anywhere else: weekdays only
    _HOLIDAYS = frozenset()

DEFAULT_PATH = os.path.join("data", "scan_telemetry.jsonl")
NEW_YORK = ZoneInfo("America/New_York")
SESSION_CLOSE = time(16, 0)
NEED_DAYS = 5


def _is_shadow_row(row: dict) -> bool:
    return (row.get("cache_mode") == "shadow" and bool(row.get("at"))
            and isinstance(row.get("cache_compared"), int)
            and isinstance(row.get("cache_diffs"), int))


def _ny_date(stamp: str) -> str:
    return _when(stamp).astimezone(NEW_YORK).date().isoformat()


def soak_days(rows: list[dict]) -> list[dict]:
    """Shadow rows summed per New York date: date, scans, compared, diffs."""
    days: dict[str, dict] = {}
    for row in filter(_is_shadow_row, rows):
        day = days.setdefault(_ny_date(row["at"]), {"scans": 0, "compared": 0, "diffs": 0})
        day["scans"] += 1
        day["compared"] += row["cache_compared"]
        day["diffs"] += row["cache_diffs"]
    return [{"date": d, **totals} for d, totals in sorted(days.items())]


def trading_day(day: str) -> bool:
    d = date.fromisoformat(day)
    return d.weekday() < 5 and d not in _HOLIDAYS


def open_day(now: datetime) -> str | None:
    """Today's New York date while its regular session is not over, else None."""
    local = now.astimezone(NEW_YORK)
    today = local.date().isoformat()
    return today if trading_day(today) and local.time() < SESSION_CLOSE else None


def counted_days(
    days: list[dict], session_open: str | None = None, *, first_full_day: str | None = None,
) -> list[str]:
    """Eligible New York trading dates with comparisons and a completed session."""
    return [
        day["date"] for day in days
        if day["compared"] > 0
        and trading_day(day["date"])
        and day["date"] != session_open
        and (first_full_day is None or day["date"] >= first_full_day)
    ]


def verdict(
    days: list[dict], need: int = NEED_DAYS, *,
    open_day: str | None = None, first_full_day: str | None = None,
) -> str:
    if any(day["diffs"] for day in days):
        return "FAIL"
    counted = counted_days(days, open_day, first_full_day=first_full_day)
    return "PASS" if len(counted) >= need else "WAIT"


def _after(rows: list[dict], since: str | None) -> list[dict]:
    if not since:
        return rows
    start = _when(since)
    return [r for r in rows if r.get("at") and _when(r["at"]) >= start]


def _parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--since", default=None, help="ISO timestamp or date (UTC)")
    parser.add_argument("--since-deploy", action="store_true", help="from the last bot deploy marker")
    parser.add_argument("--first-full-day", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="first full New York shadow session eligible to count")
    parser.add_argument("--need", type=int, default=NEED_DAYS)
    parser.add_argument("--now", default=None, help="ISO 'now' (tests and replays); default: the clock")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    if not os.path.exists(args.path):
        print(f"no telemetry file at {args.path}", file=sys.stderr)
        return 1
    rows, bad = _read(args.path)
    since = last_deploy_at(rows) if args.since_deploy else args.since
    days = soak_days(_after(rows, since))
    now = _when(args.now) if args.now else datetime.now(timezone.utc)
    current = open_day(now)
    first_full_day = args.first_full_day.isoformat() if args.first_full_day else None
    counted = counted_days(days, current, first_full_day=first_full_day)
    result = verdict(days, args.need, open_day=current, first_full_day=first_full_day)
    print(json.dumps({"days": days, "counted": counted, "need": args.need,
                      "open_day": current, "since": since, "bad_lines": bad,
                      "verdict": result}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
