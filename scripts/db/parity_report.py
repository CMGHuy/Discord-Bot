#!/usr/bin/env python3
"""Compare a migrated store's JSON file with its PostgreSQL table."""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db.import_common import ImportReport, compare  # noqa: E402


@dataclass(frozen=True)
class StoreSpec:
    filename: str
    key: str
    repo_factory: Callable[[], object]
    from_repo_shape: Callable[[dict], dict] = lambda row: row


def _trades_repo():
    from swingbot.core.db.repositories.trades import TradeRepository
    return TradeRepository()


def _trades_from_repo_shape(row: dict) -> dict:
    """Translate a normalized trades row back to its JSON-store representation."""
    from swingbot.core.tracking.performance import _json_record
    result = _json_record(row)
    for key in ("closed_at", "entry", "stop_loss"):
        result.setdefault(key, None)
    from swingbot.core.db.dual import normalise
    return normalise(result)


def _plans_repo():
    from swingbot.core.db.repositories.plans import PlanRepository
    return PlanRepository()


def _plans_from_repo_shape(row: dict) -> dict:
    from swingbot.core.db.dual import normalise
    return normalise(row)


STORES: dict[str, StoreSpec] = {
    "trades": StoreSpec("trades.json", "id", _trades_repo, _trades_from_repo_shape),
    "plans": StoreSpec("plans.json", "plan_id", _plans_repo, _plans_from_repo_shape),
}


def parity(store: str) -> ImportReport:
    """Return a strict whole-store JSON-to-Postgres parity report."""
    spec = STORES[store]
    source = read_json(os.path.join(config.DATA_DIR, spec.filename), [])
    if isinstance(source, dict):
        source = list(source.values())
    rows = [spec.from_repo_shape(row) for row in spec.repo_factory().list_all()]
    return compare(source, rows, key=spec.key)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", choices=sorted(STORES))
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    if not (args.store or args.all):
        parser.error("pass --store <name> or --all")
    failures = 0
    for name in (sorted(STORES) if args.all else [args.store]):
        report = parity(name)
        print(f"[{name}]")
        print(report.render())
        failures += not report.ok
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
