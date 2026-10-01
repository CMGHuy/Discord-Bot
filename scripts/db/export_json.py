#!/usr/bin/env python3
"""Export Postgres-backed stores back to their JSON files (v67 rollback).

The inverse of the ``import_*.py`` scripts: it makes rolling a store back from
stage ``db`` real. Reuses ``parity_report.STORES`` (file name, repository,
``from_repo_shape``) so the JSON produced here is exactly the shape parity
already treats as equal to the source.

After exporting, the bot and admin containers MUST be restarted: the
``TradeLog._trades`` / ``PlanStore._plans`` / ``StateStore._data`` singletons
hold copies from before the export and would overwrite the file on their next
write.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.dual import normalise  # noqa: E402
from swingbot.core.infra.jsonio import atomic_write_json, read_json  # noqa: E402
from scripts.db.import_common import record_checksum  # noqa: E402
from scripts.db.parity_report import STORES  # noqa: E402

RESTART_WARNING = (
    "!! RESTART the bot and admin containers NOW, before anything else writes.\n"
    "!! TradeLog._trades, PlanStore._plans and StateStore._data hold stale copies\n"
    "!! in memory and would overwrite the exported file on their next write."
)


@dataclass
class ExportResult:
    name: str
    count: int
    checksum: str
    path: str
    status: str  # written | unchanged | refused | dry-run


def _sorted_by(rows: list[dict], *keys: str) -> list[dict]:
    """Sort on string forms; a missing key sorts first rather than raising."""
    return sorted(rows, key=lambda row: tuple(str(row.get(key) or "") for key in keys))


def _rows(name: str) -> list[dict]:
    spec = STORES[name]
    return [spec.from_repo_shape(row) for row in spec.repo_factory().list_all()]


def _strip_key(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "key"}


def _shape_trades(rows: list[dict]) -> Any:
    return _sorted_by(rows, "opened_at", "id")


def _shape_plans(rows: list[dict]) -> Any:
    return _sorted_by(rows, "created_at", "plan_id")


def _shape_journal(rows: list[dict]) -> Any:
    return _sorted_by(rows, "created_at", "trade_id")


def _shape_state(rows: list[dict]) -> Any:
    return {row["key"]: _strip_key(row) for row in _sorted_by(rows, "key")}


def _shape_watchlist(rows: list[dict]) -> Any:
    return sorted(row["ticker"].upper() for row in rows)


def _shape_starred(rows: list[dict]) -> Any:
    return sorted(row["plan_id"] for row in rows)


def _without(row: dict, *keys: str) -> dict:
    return {key: value for key, value in row.items() if key not in keys}


def _shape_jobs(rows: list[dict]) -> Any:
    return {row["id"]: row for row in _sorted_by(rows, "started_at", "id")}


def _shape_scheduled(rows: list[dict]) -> Any:
    return {row["job"]: row["fired_on"] for row in _sorted_by(rows, "job")}


def _shape_preferences(rows: list[dict]) -> Any:
    owned = [row for row in rows if row.get("owner") == "admin"]
    return _without(owned[0], "owner") if owned else {}


def _shape_audit(rows: list[dict]) -> Any:
    return [{"ts": row["ts"], "changes": row.get("changes") or []}
            for row in sorted(rows, key=lambda row: row["seq"])]


def _shape_killswitch(rows: list[dict]) -> Any:
    return _without(rows[0], "key") if rows else {}


def _shape_tuning(rows: list[dict]) -> Any:
    return {f"{row['job_id']}.json": _without(row, "job_id", "created_at")
            for row in _sorted_by(rows, "job_id")}


def _shape_proposals(rows: list[dict]) -> Any:
    return {row["filename"]: _without(row, "filename") for row in _sorted_by(rows, "filename")}


def _build_ticker_directory() -> Any:
    from swingbot.core.db.repositories.ticker_directory import TickerDirectoryRepository
    repo = TickerDirectoryRepository()
    return {"fetched_at": repo.loaded_at(), "rows": _sorted_by(_rows("ticker_directory"), "symbol")}


def _build_account() -> Any:
    from swingbot.core.db.repositories.account import AccountRepository
    repo = AccountRepository()
    payload = normalise(repo.load())
    history = _sorted_by([normalise(entry) for entry in repo.history()], "ts")
    if history or payload:
        payload["balance_history"] = history
    return payload


SHAPERS: dict[str, Callable[[list[dict]], Any]] = {
    "trades": _shape_trades, "plans": _shape_plans, "journal": _shape_journal,
    "state": _shape_state, "watchlist": _shape_watchlist,
    "starred_plans": _shape_starred,
    # v116: Part 3.
    "jobs": _shape_jobs, "scheduled_jobs": _shape_scheduled,
    "preferences": _shape_preferences, "settings_audit": _shape_audit,
    "killswitch": _shape_killswitch, "tuning": _shape_tuning,
    "tuning_proposals": _shape_proposals,
}

#: Stores whose document is not a function of their rows alone.
BUILDERS: dict[str, Callable[[], Any]] = {
    "account": _build_account, "ticker_directory": _build_ticker_directory,
}

#: How a store lands on disk; absent means one JSON document ("file").
KINDS: dict[str, str] = {"settings_audit": "jsonl", "tuning": "dir", "tuning_proposals": "dir"}


def _kind(name: str) -> str:
    return KINDS.get(name, "file")


def _write_jsonl(path: str, payload: list) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        for entry in payload:
            handle.write(json.dumps(entry) + "\n")
    os.replace(tmp, path)


def _write_dir(path: str, payload: dict) -> None:
    """The table is the truth: a file it no longer has is removed."""
    os.makedirs(path, exist_ok=True)
    for name in os.listdir(path):
        if name.endswith(".json") and name not in payload:
            os.remove(os.path.join(path, name))
    for name, content in payload.items():
        atomic_write_json(os.path.join(path, name), content)


WRITERS: dict[str, Callable[[str, Any], None]] = {
    "file": atomic_write_json, "jsonl": _write_jsonl, "dir": _write_dir,
}


def _read_jsonl(path: str) -> list | None:
    entries = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _read_dir(path: str) -> dict:
    return {name: read_json(os.path.join(path, name), None)
            for name in sorted(os.listdir(path)) if name.endswith(".json")}


_READERS = {"file": lambda path: read_json(path, None), "jsonl": _read_jsonl, "dir": _read_dir}


def build_payload(name: str) -> Any:
    """Return the JSON-ready document for one store, in on-disk shape."""
    if name in BUILDERS:
        return normalise(BUILDERS[name]())
    return normalise(SHAPERS[name](_rows(name)))


def _record_count(name: str, payload: Any) -> int:
    if name == "account":
        return len(payload.get("balance_history", [])) + (1 if payload else 0)
    if name == "ticker_directory":
        return len(payload.get("rows", []))
    return len(payload)


def _sidecar(path: str, kind: str) -> str:
    if kind == "dir":
        return f"{path}.exported"
    stem, ext = os.path.splitext(path)
    return f"{stem}.exported{ext}"


def _decide(path: str, kind: str, checksum: str, force: bool) -> tuple[str, str]:
    """Return (status, target_path) for a write to ``path``."""
    if not os.path.exists(path):
        return "written", path
    if record_checksum({"v": _READERS[kind](path)}) == checksum:
        return "unchanged", path
    return ("written", path) if force else ("refused", _sidecar(path, kind))


def export_one(name: str, out_dir: str, *, dry_run: bool, force: bool) -> ExportResult:
    payload = build_payload(name)
    checksum = record_checksum({"v": payload})
    kind = _kind(name)
    path = os.path.join(out_dir, STORES[name].filename)
    status, target = _decide(path, kind, checksum, force)
    if dry_run:
        status = "dry-run"
    elif status != "unchanged":
        WRITERS[kind](target, payload)
    return ExportResult(name, _record_count(name, payload), checksum, target, status)


def exportable_names() -> list[str]:
    return sorted(name for name in STORES if name in BUILDERS or name in SHAPERS)


def run_export(names: list[str], out_dir: str, *, dry_run: bool, force: bool) -> list[ExportResult]:
    exportable = exportable_names()
    selected = exportable if "all" in names else names
    unshaped = [name for name in selected if name not in exportable]
    if unshaped:
        raise SystemExit(f"export_json: no JSON shaper for store(s): {', '.join(unshaped)}")
    os.makedirs(out_dir, exist_ok=True)
    return [export_one(name, out_dir, dry_run=dry_run, force=force) for name in selected]


def _print_result(result: ExportResult) -> None:
    print(f"[{result.name}] {result.count} record(s)  sha256={result.checksum}  "
          f"{result.status.upper()} -> {result.path}")
    if result.status == "refused":
        print(f"[{result.name}] target exists and differs; NOT overwritten "
              f"(re-run with --force). Export left beside it.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export Postgres stores back to JSON")
    parser.add_argument("--store", required=True, choices=sorted(STORES) + ["all"])
    parser.add_argument("--out-dir", default=None, help="default: config.DATA_DIR")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="overwrite a differing existing file")
    args = parser.parse_args(argv)
    results = run_export([args.store], args.out_dir or config.DATA_DIR,
                         dry_run=args.dry_run, force=args.force)
    for result in results:
        _print_result(result)
    if not args.dry_run:
        print(RESTART_WARNING)
    return int(any(result.status == "refused" for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
