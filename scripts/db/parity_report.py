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
    loader: Callable[[object], list[dict]] | None = None
    ignore_fields: frozenset[str] = frozenset()


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
    """Translate a plans row back to its JSON-store representation.

    `created_at` is a promoted timestamptz, so a date-only source string comes
    back widened to a full ISO instant. Every consumer treats the field as an
    opaque string or parses either form (api_v1/trades.py passes it through,
    rank._parse_created_at accepts date or datetime, the SPA types it
    `string | null` and feeds it to age()/asText()), so the honest round trip
    is to render midnight UTC back to the date it was written as. A timestamp
    with a real time of day is left alone; only the widening is undone.
    """
    import datetime as dt

    from swingbot.core.db.dual import normalise

    out = dict(row)
    created = out.get("created_at")
    if isinstance(created, dt.datetime) and created.tzinfo is not None:
        midnight = (created.time() == dt.time(0)
                    and created.utcoffset() == dt.timedelta(0))
        out["created_at"] = created.date().isoformat() if midnight else created.isoformat()
    return normalise(out)


def _starred_repo():
    from swingbot.core.db.repositories.starred import StarredRepository
    return StarredRepository()


def _starred_rows(raw: object) -> list[dict]:
    return [{"plan_id": value} for value in raw]


def _account_repo():
    from swingbot.core.db.repositories.account import AccountRepository
    return AccountRepository()


def _account_rows(raw: object) -> list[dict]:
    cfg = dict(raw) if isinstance(raw, dict) else {}
    cfg.pop("balance_history", None)
    return [{"key": "config", **cfg}]


def _journal_repo():
    from swingbot.core.db.repositories.journal import JournalRepository
    return JournalRepository()


def _journal_from_repo_shape(row: dict) -> dict:
    from swingbot.core.db.dual import normalise
    return normalise(row)


def _state_repo():
    from swingbot.core.db.repositories.signal_state import SignalStateRepository
    return SignalStateRepository()


def _state_rows(raw: object) -> list[dict]:
    return [{"key": key, **value} for key, value in raw.items()]


def _watchlist_repo():
    from swingbot.core.db.repositories.watchlist import WatchlistRepository
    return WatchlistRepository()


def _watchlist_rows(raw: object) -> list[dict]:
    return [{"ticker": ticker} for ticker in raw]


def _watchlist_from_repo_shape(row: dict) -> dict:
    from swingbot.core.db.dual import normalise
    return normalise(row)


STORES: dict[str, StoreSpec] = {
    "account": StoreSpec("account.json", "key", _account_repo, loader=_account_rows),
    "journal": StoreSpec("journal.json", "trade_id", _journal_repo,
                         _journal_from_repo_shape),
    "trades": StoreSpec("trades.json", "id", _trades_repo, _trades_from_repo_shape),
    "plans": StoreSpec("plans.json", "plan_id", _plans_repo, _plans_from_repo_shape),
    "starred_plans": StoreSpec("starred_plans.json", "plan_id", _starred_repo,
                                loader=_starred_rows),
    "state": StoreSpec("state.json", "key", _state_repo, loader=_state_rows),
    "watchlist": StoreSpec("watchlist.json", "ticker", _watchlist_repo,
                             _watchlist_from_repo_shape, _watchlist_rows,
                             frozenset({"added_at"})),
}


def parity(store: str, source_path: str | None = None) -> ImportReport:
    """Return a strict whole-store JSON-to-Postgres parity report.

    ``source_path`` mirrors the importers' ``--source`` flag: verification must
    read the same file the import read, or it is checking the wrong thing.
    """
    spec = STORES[store]
    source = read_json(source_path or os.path.join(config.DATA_DIR, spec.filename), [])
    if spec.loader is not None:
        source = spec.loader(source)
    if isinstance(source, dict):
        source = list(source.values())
    rows = [spec.from_repo_shape(row) for row in spec.repo_factory().list_all()]
    return compare(source, rows, key=spec.key, ignore_fields=spec.ignore_fields)


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
