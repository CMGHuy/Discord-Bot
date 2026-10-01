"""Rollback readiness on the real book (v116 Phase 3; the schema-change
skill's gate). Each production file is written through its importer, read
back through its repository and compared by parity; then exported and
compared again -- so db -> json is proven on production data, not a fixture.

Skips without a snapshot (bash scripts/ops/pull_prod_snapshot.sh) or db-test."""
import json
import os
import pathlib

import pytest

from scripts.db import export_json
from scripts.db import (import_jobs, import_journal, import_killswitch, import_plans,
                        import_preferences, import_scheduled, import_settings_audit,
                        import_starred, import_state, import_ticker_directory, import_trades,
                        import_tuning, import_watchlist)
from scripts.db.parity_report import STORES, parity
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.flags import FLAGS, flags_repo
from swingbot.core.db.repositories.heartbeat import heartbeat_repo
from swingbot.core.db.repositories.market_data_state import market_data_state_repo
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.scan_progress import scan_progress_repo
from swingbot.core.db.repositories.settings_audit import SettingsAuditRepository
from swingbot.core.db.repositories.tuning import ProposalRepository, TuningRepository

REPO = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT = pathlib.Path(os.getenv("V116_SNAPSHOT_DIR", REPO / "data" / "v116_snapshot"))
pytestmark = pytest.mark.skipif(
    not (SNAPSHOT / "PULLED_AT").exists(),
    reason="no production snapshot; run: bash scripts/ops/pull_prod_snapshot.sh")

#: store -> (load_source(path) -> rows, repository factory, write_one, prepare or None).
#: plans before starred_plans (foreign key).
IMPORTS = {
    "watchlist": (import_watchlist.load_source, STORES["watchlist"].repo_factory, import_watchlist.write_one, None),
    "state": (import_state.load_source, STORES["state"].repo_factory, import_state.write_one, None),
    "plans": (import_plans.load_source, STORES["plans"].repo_factory, import_plans.write_one, None),
    "starred_plans": (import_starred.load_source, STORES["starred_plans"].repo_factory, import_starred.write_one, None),
    "trades": (import_trades.load_source, STORES["trades"].repo_factory, import_trades.write_one, None),
    "journal": (import_journal.load_source, STORES["journal"].repo_factory, import_journal.write_one, None),
    "jobs": (import_jobs.load_source, STORES["jobs"].repo_factory, import_jobs.write_one, None),
    "scheduled_jobs": (import_scheduled.load_source, STORES["scheduled_jobs"].repo_factory, import_scheduled.write_one, None),
    "preferences": (import_preferences.load_source, STORES["preferences"].repo_factory, import_preferences.write_one, None),
    "settings_audit": (import_settings_audit.load_source, SettingsAuditRepository, import_settings_audit.write_one, import_settings_audit.prepare),
    "killswitch": (import_killswitch.load_source, STORES["killswitch"].repo_factory, import_killswitch.write_one, None),
    "ticker_directory": (import_ticker_directory.load_source, STORES["ticker_directory"].repo_factory, import_ticker_directory.write_one, None),
    "tuning": (import_tuning.load_results, TuningRepository, import_tuning.write_one, None),
    "tuning_proposals": (import_tuning.load_proposals, ProposalRepository, import_tuning.write_one, None),
}


def _import(name: str, source: str) -> None:
    load, factory, write_one, prepare = IMPORTS[name]
    repo = factory()
    if prepare is not None:
        prepare(repo)
    for record in load(source):
        write_one(repo, record)


def test_every_parity_store_round_trips_production_data(store_db, tmp_path):
    failures, seen = {}, []
    account = SNAPSHOT / "account.json"
    if account.exists():
        AccountRepository().save(json.loads(account.read_text(encoding="utf-8")))
    for name in IMPORTS:
        source = SNAPSHOT / STORES[name].filename
        if not source.exists():
            continue
        seen.append(name)
        _import(name, str(source))
        imported = parity(name, source_path=str(source))
        if not imported.ok:
            failures[f"{name}: import"] = imported.render()
            continue
        export_json.run_export([name], str(tmp_path), dry_run=False, force=True)
        exported = parity(name, source_path=str(tmp_path / STORES[name].filename))
        if not exported.ok:
            failures[f"{name}: export"] = exported.render()
    assert seen, "the snapshot holds none of the store files"
    assert not failures, "\n".join(f"[{key}]\n{value}" for key, value in failures.items())


def _load(name):
    path = SNAPSHOT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def test_the_ops_stores_round_trip_production_data(store_db, tmp_path):
    state = _load("market_data_state.json")
    if state is not None:
        market_data_state_repo().save(state)
    heartbeat = _load("bot_heartbeat.json")
    if heartbeat is not None:
        heartbeat_repo().beat(heartbeat)
    for record in _load("manual_close_notify.json") or []:
        NotifyQueueRepository().enqueue(record)
    progress = _load("scan_progress.json")
    if progress is not None:
        scan_progress_repo().publish(progress)
    raised = [name for name in FLAGS if (SNAPSHOT / f"{name}.flag").exists()]
    for name in raised:
        flags_repo().set(name)

    export_json.run_export(list(export_json.EXTRA), str(tmp_path), dry_run=False, force=True)

    if state is not None:
        assert _json(tmp_path / "market_data_state.json") == state
    if heartbeat is not None:
        exported = _json(tmp_path / "bot_heartbeat.json")
        assert {key: exported.get(key) for key in heartbeat} == heartbeat
    assert (_json(tmp_path / "manual_close_notify.json") or []) == (_load("manual_close_notify.json") or [])
    if progress is not None:
        assert _json(tmp_path / "scan_progress.json") == progress
    assert sorted(p.stem for p in tmp_path.glob("*.flag")) == sorted(raised)


def _json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
