#!/usr/bin/env python3
"""v220 rollback window: doc-key snapshot at rollback, rows changed during it at release.

    python3 rollback_window.py snapshot --out FILE [--app-dir DIR]
    python3 rollback_window.py report --snapshot FILE --since TS --until TS [--app-dir DIR]

Reads Postgres through `docker compose exec db psql` with every transaction read-only.
Key NAMES only, never values. Standard library only: the VM host's python3 runs it
from a copy outside the checkout.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

TABLES = ("plans", "journal_entries")
_KEYS = "COALESCE((SELECT string_agg(k, ',' ORDER BY k) FROM jsonb_object_keys(doc) AS k), '')"
KEYS_SQL = (f"SELECT 'plans', plan_id, {_KEYS} FROM plans\n"
            f"UNION ALL SELECT 'journal_entries', trade_id, {_KEYS} FROM journal_entries\n")
UPDATED_SQL = (f"SELECT 'plans', plan_id, {_KEYS} FROM plans\n"
               "  WHERE updated_at >= '{since}' AND updated_at <= '{until}'\n"
               f"UNION ALL SELECT 'journal_entries', trade_id, {_KEYS} FROM journal_entries\n"
               "  WHERE updated_at >= '{since}' AND updated_at <= '{until}'\n")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PSQL = ("docker", "compose", "exec", "-T", "-e", "PGOPTIONS=-c default_transaction_read_only=on", "db",
         "psql", "-X", "-U", "swingbot", "-d", "swingbot", "-v", "ON_ERROR_STOP=1", "-A", "-t", "-F", "\t", "-c")
_RUN = subprocess.run  # test seam for the CLI


def _psql(sql: str, app_dir: Path, run) -> list[str]:
    done = run([*_PSQL, sql], cwd=str(app_dir), capture_output=True, text=True,
               encoding="utf-8", check=True)
    return [line for line in done.stdout.splitlines() if line.strip()]


def _key_map(lines: list[str]) -> dict[str, dict[str, list[str]]]:
    """table -> {row id -> sorted doc key names}; rows of other tables are ignored."""
    found: dict[str, dict[str, list[str]]] = {table: {} for table in TABLES}
    for line in lines:
        table, _, rest = line.partition("\t")
        row_id, _, keys = rest.partition("\t")
        if table in found and row_id:
            found[table][row_id] = sorted(k for k in keys.split(",") if k)
    return found


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def keys_snapshot(*, app_dir: Path, run=subprocess.run) -> dict:
    """{"at", "plans": {id: [keys]}, "journal_entries": {id: [keys]}} for every row."""
    return {"at": _now(), **_key_map(_psql(KEYS_SQL, Path(app_dir), run))}


def updated_sql(since: str, until: str) -> str:
    for value in (since, until):
        if not _TS.match(value or ""):
            raise ValueError(f"timestamp must be YYYY-MM-DDTHH:MM:SSZ, got {value!r}")
    return UPDATED_SQL.format(since=since, until=until)


def _table_report(before: dict, now: dict, ids: list[str]) -> dict:
    fewer = []
    for row_id in sorted(set(ids) & set(before)):
        after = now.get(row_id, [])
        dropped = sorted(set(before[row_id]) - set(after))
        if dropped:
            fewer.append({"id": row_id, "before": len(before[row_id]), "after": len(after), "dropped": dropped})
    return {"updated": len(ids), "new": len(set(ids) - set(before)), "fewer_keys": fewer}


def window_report(snapshot: dict, current: dict, updated: dict[str, list[str]]) -> dict:
    """Rows updated in the window, new rows, and pre-window rows that lost doc keys."""
    return {"tables": {table: _table_report(snapshot.get(table, {}), current.get(table, {}),
                                            list(updated.get(table, [])))
                       for table in TABLES}}


def _cmd_snapshot(args: argparse.Namespace) -> int:
    snap = keys_snapshot(app_dir=Path(args.app_dir), run=_RUN)
    out = Path(args.out)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(snap, sort_keys=True), encoding="utf-8")
    tmp.replace(out)
    counts = ", ".join(f"{table} {len(snap[table])}" for table in TABLES)
    print(f"snapshot {out}: {counts}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    sql = updated_sql(args.since, args.until)
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    current = _key_map(_psql(sql, Path(args.app_dir), _RUN))
    updated = {table: sorted(rows) for table, rows in current.items()}
    print(json.dumps(window_report(snapshot, current, updated), indent=2, sort_keys=True))
    return 0


HANDLERS = {"snapshot": _cmd_snapshot, "report": _cmd_report}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v220 rollback-window snapshot and report")
    sub = parser.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot", help="doc key names of every plans/journal_entries row")
    snap.add_argument("--out", required=True)
    rep = sub.add_parser("report", help="rows updated during the window vs the snapshot")
    rep.add_argument("--snapshot", required=True)
    rep.add_argument("--since", required=True)
    rep.add_argument("--until", required=True)
    for cmd in (snap, rep):
        cmd.add_argument("--app-dir", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return HANDLERS[args.cmd](args)
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        detail = getattr(exc, "stderr", None) or exc
        print(f"window report failed: {str(detail).strip()}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
