"""Seed stores through their real importers (v116 Phase 4).

Every store lives in Postgres, so a test that used to write data/<store>.json
calls seed_store("<store>", <the same payload>) instead. The payload keeps the
on-disk JSON shape; the importer does the translation the production import
did, so a fixture cannot drift from what the bot reads."""
import json
import os
import tempfile

from scripts.db import (import_jobs, import_journal, import_killswitch, import_plans,
                        import_preferences, import_scheduled, import_settings_audit,
                        import_starred, import_state, import_ticker_directory, import_trades,
                        import_tuning, import_watchlist)
from scripts.db.parity_report import STORES
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.settings_audit import SettingsAuditRepository
from swingbot.core.db.repositories.tuning import ProposalRepository, TuningRepository

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


def _write_source(directory: str, name: str, payload) -> str:
    path = os.path.join(directory, STORES[name].filename)
    if name in ("tuning", "tuning_proposals"):
        os.makedirs(path)
        for filename, content in payload.items():
            with open(os.path.join(path, filename), "w", encoding="utf-8") as handle:
                json.dump(content, handle)
    elif name == "settings_audit":
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(json.dumps(entry) + "\n" for entry in payload)
    else:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    return path


def seed_store(name: str, payload) -> None:
    if name == "account":
        AccountRepository().save(payload)
        return
    load, factory, write_one, prepare = IMPORTS[name]
    repo = factory()
    if prepare is not None:
        prepare(repo)
    with tempfile.TemporaryDirectory() as directory:
        for record in load(_write_source(directory, name, payload)):
            write_one(repo, record)
