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
    #: True when the store is a JSONL file or a directory of files, so the
    #: loader is handed the path instead of a parsed JSON document.
    loader_takes_path: bool = False


def _trades_repo():
    from swingbot.core.db.repositories.trades import TradeRepository
    return TradeRepository()


def _trades_from_repo_shape(row: dict) -> dict:
    """Translate a normalized trades row back to its JSON-store representation."""
    from swingbot.core.tracking.performance import _json_record
    result = _json_record(row)
    for key in ("closed_at", "entry", "stop_loss"):
        result.setdefault(key, None)
    from swingbot.core.db.codec import normalise
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

    from swingbot.core.db.codec import normalise

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
    from swingbot.core.db.codec import normalise
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
    from swingbot.core.db.codec import normalise
    return normalise(row)


def _utc_iso(value):
    """Render a timestamptz back to the ISO string the JSON stores wrote."""
    import datetime as dt
    if isinstance(value, dt.datetime) and value.tzinfo is not None:
        return value.astimezone(dt.timezone.utc).isoformat()
    return value.isoformat() if hasattr(value, "isoformat") else value


def _jobs_repo():
    from swingbot.core.db.repositories.jobs import JobRepository
    return JobRepository()


def _jobs_rows(raw: object) -> list[dict]:
    from scripts.db.part3_sources import jobs_rows
    return jobs_rows(raw)


def _jobs_from_repo_shape(row: dict) -> dict:
    """Undo the storage split: `job_id` is the file's `id`, `status` its `state`."""
    out = dict(row)
    out["id"] = out.pop("job_id")
    out.pop("status", None)
    out["started_at"] = _utc_iso(out.get("started_at"))
    out["finished_at"] = _utc_iso(out.get("finished_at"))
    return out


def _scheduled_repo():
    from swingbot.core.db.repositories.scheduled import ScheduledJobRepository
    return ScheduledJobRepository()


def _scheduled_rows(raw: object) -> list[dict]:
    from scripts.db.part3_sources import scheduled_rows
    return scheduled_rows(raw)


def _preferences_repo():
    from swingbot.core.db.repositories.preferences import PreferencesRepository
    return PreferencesRepository()


def _preferences_rows(raw: object) -> list[dict]:
    from scripts.db.part3_sources import preferences_rows
    return preferences_rows(raw)


class _OrderedAuditRepo:
    """The audit table in insertion order, each row numbered like the file's."""

    def list_all(self) -> list[dict]:
        from swingbot.core.db.repositories.settings_audit import SettingsAuditRepository
        from swingbot.core.db.schema import settings_audit
        rows = SettingsAuditRepository().list_all(order_by=settings_audit.c.id.asc())
        return [{"seq": index, **row} for index, row in enumerate(rows)]


def _audit_rows(path: object) -> list[dict]:
    from scripts.db.part3_sources import audit_rows
    return audit_rows(path)


def _audit_from_repo_shape(row: dict) -> dict:
    return {"seq": row["seq"], "ts": _utc_iso(row.get("ts")),
            "changes": row.get("changes") or []}


def _killswitch_repo():
    from swingbot.core.db.repositories.killswitch import KillswitchRepository
    return KillswitchRepository()


def _killswitch_rows(raw: object) -> list[dict]:
    from scripts.db.part3_sources import killswitch_rows
    return killswitch_rows(raw)


def _killswitch_from_repo_shape(row: dict) -> dict:
    """The table's `engaged`/`engaged_at` are the file's `on`/`at`."""
    return {"key": row["key"], "on": bool(row.get("engaged")),
            "reason": row.get("reason"), "at": _utc_iso(row.get("engaged_at")),
            "manual_release": bool(row.get("manual_release"))}


def _ticker_repo():
    from swingbot.core.db.repositories.ticker_directory import TickerDirectoryRepository
    return TickerDirectoryRepository()


def _ticker_rows(raw: object) -> list[dict]:
    from scripts.db.part3_sources import ticker_rows
    return ticker_rows(raw)


def _tuning_repo():
    from swingbot.core.db.repositories.tuning import TuningRepository
    return TuningRepository()


def _tuning_rows(path: object) -> list[dict]:
    from scripts.db.part3_sources import tuning_result_rows
    return tuning_result_rows(path)


def _proposals_repo():
    from swingbot.core.db.repositories.tuning import ProposalRepository
    return ProposalRepository()


def _proposal_rows(path: object) -> list[dict]:
    from scripts.db.part3_sources import proposal_rows
    return proposal_rows(path)


def _proposal_from_repo_shape(row: dict) -> dict:
    return {**row, "created_at": _utc_iso(row.get("created_at"))}


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
    "jobs": StoreSpec("admin_jobs.json", "id", _jobs_repo, _jobs_from_repo_shape,
                      _jobs_rows),
    "scheduled_jobs": StoreSpec("scheduled_jobs.json", "job", _scheduled_repo,
                                loader=_scheduled_rows),
    "preferences": StoreSpec("ui_preferences.json", "owner", _preferences_repo,
                             loader=_preferences_rows),
    "settings_audit": StoreSpec("settings_audit.jsonl", "seq", _OrderedAuditRepo,
                                _audit_from_repo_shape, _audit_rows,
                                loader_takes_path=True),
    "killswitch": StoreSpec("killswitch.json", "key", _killswitch_repo,
                            _killswitch_from_repo_shape, _killswitch_rows),
    "ticker_directory": StoreSpec("ticker_directory.json", "symbol", _ticker_repo,
                                  loader=_ticker_rows),
    # created_at is stamped at import (a result file records none), so there is
    # nothing in the source to compare it with.
    "tuning": StoreSpec("tuning_results", "job_id", _tuning_repo, loader=_tuning_rows,
                        ignore_fields=frozenset({"created_at"}),
                        loader_takes_path=True),
    "tuning_proposals": StoreSpec("tuning_proposals", "filename", _proposals_repo,
                                  _proposal_from_repo_shape, _proposal_rows,
                                  loader_takes_path=True),
}


def parity(store: str, source_path: str | None = None) -> ImportReport:
    """Return a strict whole-store JSON-to-Postgres parity report.

    ``source_path`` mirrors the importers' ``--source`` flag: verification must
    read the same file the import read, or it is checking the wrong thing.
    """
    spec = STORES[store]
    path = source_path or os.path.join(config.DATA_DIR, spec.filename)
    source = path if spec.loader_takes_path else read_json(path, [])
    if spec.loader is not None:
        source = spec.loader(source)
    if isinstance(source, dict):
        source = list(source.values())
    rows = [spec.from_repo_shape(row) for row in spec.repo_factory().list_all()]
    return compare(source, rows, key=spec.key, ignore_fields=spec.ignore_fields)


def _selected(args) -> list[str]:
    return sorted(STORES) if args.all else [args.store]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", choices=sorted(STORES))
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    if not (args.store or args.all):
        parser.error("pass --store <name> or --all")
    names = _selected(args)
    failures = 0
    for name in names:
        report = parity(name)
        print(f"[{name}]")
        print(report.render())
        failures += not report.ok
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
