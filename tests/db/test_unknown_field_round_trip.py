"""A record carrying a field no code has ever seen is written through every
repository and read back unchanged -- nested objects and lists included
(v116 Phase 2). This is the property that makes "add a field" a code-only
change; a repository that drops or mangles unknown keys breaks it."""
import pytest

from swingbot.core.db import schema
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.flags import FlagRepository
from swingbot.core.db.repositories.heartbeat import HeartbeatRepository
from swingbot.core.db.repositories.jobs import JobRepository
from swingbot.core.db.repositories.journal import JournalRepository
from swingbot.core.db.repositories.killswitch import KillswitchRepository
from swingbot.core.db.repositories.market_data_state import MarketDataStateRepository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.preferences import PreferencesRepository
from swingbot.core.db.repositories.scan_progress import ScanProgressRepository
from swingbot.core.db.repositories.scheduled import ScheduledJobRepository
from swingbot.core.db.repositories.settings_audit import SettingsAuditRepository
from swingbot.core.db.repositories.signal_state import SignalStateRepository
from swingbot.core.db.repositories.starred import StarredRepository
from swingbot.core.db.repositories.ticker_directory import TickerDirectoryRepository
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.repositories.tuning import ProposalRepository, TuningRepository
from swingbot.core.db.repositories.watchlist import WatchlistRepository

TS = "2026-10-01T10:00:00+00:00"
PROBE = {"nested": {"list": [1, {"deep": "x"}, None], "flag": True},
         "tags": ["a", "b"], "ratio": 0.125, "empty": {}}
PLAN = {"plan_id": "P-probe", "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
        "status": "pending", "created_at": TS}

#: table -> (repository factory, the NOT NULL promoted values a row needs)
CASES = {
    "trades": (TradeRepository, {"trade_id": "T-probe", "ticker": "AAPL", "strategy": "RSI",
                                 "horizon": "2w", "direction": "bullish", "status": "open",
                                 "opened_at": TS}),
    "plans": (PlanRepository, PLAN),
    "starred_plans": (StarredRepository, {"plan_id": "P-probe"}),
    "account": (AccountRepository, {"key": "config"}),
    "account_balance_history": (lambda: AccountRepository()._history, {"ts": TS, "balance": 1000.0}),
    "journal_entries": (JournalRepository, {"trade_id": "T-probe", "created_at": TS}),
    "signal_state": (SignalStateRepository, {"key": "AAPL|RSI|2w"}),
    "watchlist": (WatchlistRepository, {"ticker": "AAPL", "added_at": TS}),
    "runtime_flags": (FlagRepository, {"name": "scan_paused", "set_at": TS}),
    "bot_heartbeat": (HeartbeatRepository, {"key": "bot", "ts": TS}),
    "admin_jobs": (JobRepository, {"job_id": "J-probe", "kind": "tune", "status": "done",
                                   "started_at": TS}),
    "scheduled_jobs": (ScheduledJobRepository, {"job": "recap", "fired_on": "2026-10-01"}),
    "ui_preferences": (PreferencesRepository, {"owner": "admin"}),
    "settings_audit": (SettingsAuditRepository, {"ts": TS}),
    "killswitch": (KillswitchRepository, {"key": "global", "engaged": False}),
    "manual_close_notify": (NotifyQueueRepository, {"queued_at": TS}),
    "ticker_directory": (TickerDirectoryRepository, {"symbol": "AAPL", "name": "Apple"}),
    "tuning_results": (TuningRepository, {"job_id": "J-probe", "created_at": TS}),
    "tuning_proposals": (ProposalRepository, {"filename": "p.json", "created_at": TS}),
    "scan_progress": (ScanProgressRepository, {"key": "current"}),
    "market_data_state": (MarketDataStateRepository, {"key": "AAPL|daily"}),
}

#: Tables with no repository, and why. Anything else must be in CASES.
NOT_REPOSITORY_BACKED = {
    "dropped_doc_fields": "written only by swingbot.core.db.doc_fields inside Alembic revisions",
}


def _write(repo, record, conn):
    # Surrogate-keyed tables (append-only) insert; natural keys upsert.
    if repo.key == "id":
        return repo.insert(record, conn=conn)
    return repo.upsert(record, conn=conn)


@pytest.mark.parametrize("table", sorted(CASES))
def test_an_unseen_field_round_trips_unchanged(table, db_conn):
    factory, required = CASES[table]
    if table == "starred_plans":
        PlanRepository().upsert(dict(PLAN), conn=db_conn)   # its foreign key
    repo = factory()
    assert repo.table.name == table
    _write(repo, {**required, "_v116_probe": PROBE}, db_conn)
    rows = [row for row in repo.list_all(conn=db_conn) if "_v116_probe" in row]
    assert len(rows) == 1
    assert rows[0]["_v116_probe"] == PROBE


def test_every_table_is_covered_or_excused():
    assert set(schema.METADATA.tables) <= set(CASES) | set(NOT_REPOSITORY_BACKED)
