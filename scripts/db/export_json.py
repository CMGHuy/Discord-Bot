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
}


def build_payload(name: str) -> Any:
    """Return the JSON-ready document for one store, in on-disk shape."""
    if name == "account":
        return _build_account()
    return SHAPERS[name](_rows(name))


def _record_count(name: str, payload: Any) -> int:
    if name == "account":
        return len(payload.get("balance_history", [])) + (1 if payload else 0)
    return len(payload)


def _sidecar(path: str) -> str:
    stem, ext = os.path.splitext(path)
    return f"{stem}.exported{ext}"


def _decide(path: str, checksum: str, force: bool) -> tuple[str, str]:
    """Return (status, target_path) for a write to ``path``."""
    if not os.path.exists(path):
        return "written", path
    if record_checksum({"v": read_json(path, None)}) == checksum:
        return "unchanged", path
    return ("written", path) if force else ("refused", _sidecar(path))


def export_one(name: str, out_dir: str, *, dry_run: bool, force: bool) -> ExportResult:
    payload = build_payload(name)
    checksum = record_checksum({"v": payload})
    path = os.path.join(out_dir, STORES[name].filename)
    # `checksum` covers {"v": payload}; _decide hashes the file the same way.
    status, target = _decide(path, checksum, force)
    if dry_run:
        status = "dry-run"
    elif status != "unchanged":
        atomic_write_json(target, payload)
    return ExportResult(name, _record_count(name, payload), checksum, target, status)


def run_export(names: list[str], out_dir: str, *, dry_run: bool, force: bool) -> list[ExportResult]:
    selected = sorted(STORES) if "all" in names else names
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
