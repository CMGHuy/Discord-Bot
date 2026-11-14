"""A record carrying a field no code has ever seen is written through every
repository and read back unchanged -- nested objects and lists included
(v116 Phase 2). This is the property that makes "add a field" a code-only
change; a repository that drops or mangles unknown keys breaks it."""
import pytest

from swingbot.core.db import schema
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.admin_users import AdminUsersRepository
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.benchmark_bars import (
    BenchmarkBarRepository, BenchmarkRefreshRepository)
from swingbot.core.db.repositories.equity_samples import EquitySampleRepository
from swingbot.core.db.repositories.flags import FlagRepository
from swingbot.core.db.repositories.gate_rejections import GateRejectionRepository
from swingbot.core.db.repositories.heartbeat import HeartbeatRepository
from swingbot.core.db.repositories.jobs import JobRepository
from swingbot.core.db.repositories.journal import JournalRepository
from swingbot.core.db.repositories.killswitch import KillswitchRepository
from swingbot.core.db.repositories.market_data_state import MarketDataStateRepository
from swingbot.core.db.repositories.market_shared import MarketSharedRepository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.market_refresh import (
    QuoteCurrencyRepository, RefresherHeartbeatRepository, RefreshMarkRepository,
    RefreshQueueRepository)
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
    "manual_close_notify": (NotifyQueueRepository, {"queued_at": TS, "event_id": "round-trip", "next_attempt_at": TS}),
    "ticker_directory": (TickerDirectoryRepository, {"symbol": "AAPL", "name": "Apple"}),
    "tuning_results": (TuningRepository, {"job_id": "J-probe", "created_at": TS}),
    "tuning_proposals": (ProposalRepository, {"filename": "p.json", "created_at": TS}),
    "scan_progress": (ScanProgressRepository, {"key": "current"}),
    "market_data_state": (MarketDataStateRepository, {"key": "AAPL|daily"}),
    # v152: the base surrogate-keyed Repository over each new table. The
    # V152-3/V152-4 classes subclass it; the property under test is the base
    # insert/list path every one of them reads back through.
    "plan_followers": (lambda: Repository(schema.plan_followers, key="id"),
                       {"plan_id": "P-probe", "user_id": 123456789012345678, "kind": "watch"}),
    "plan_notifications": (lambda: Repository(schema.plan_notifications, key="id"),
                           {"plan_id": "P-probe", "event": "tp1", "state": "pending"}),
    "notify_prefs": (lambda: Repository(schema.notify_prefs, key="id"),
                     {"user_id": 123456789012345678}),
    "alert_posts": (lambda: Repository(schema.alert_posts, key="id"),
                    {"ticker": "AAPL", "at": TS, "outcome": "posted"}),
    "gate_rejections": (GateRejectionRepository, {"ticker": "AAPL", "gate": "rs", "strategy": "RSI",
                                                  "horizon": "2w", "signal_date": "2026-10-01",
                                                  "cf_status": "pending", "created_at": TS}),
    "market_cache": (lambda: MarketSharedRepository().cache,
                     {"key": "quote:AAPL:", "kind": "quote", "symbol": "AAPL"}),
    "provider_budget": (lambda: MarketSharedRepository().budget,
                        {"provider": "alpaca", "tokens": 150.0, "stamp": TS}),
    "market_fetch_counts": (lambda: MarketSharedRepository().counts,
                            {"hour": TS, "provider": "alpaca", "kind": "quote", "asker": "scan",
                             "outcome": "hit", "n": 1}),
    "equity_samples": (EquitySampleRepository, {"at": TS, "realized_balance": 0.0, "unrealized_pnl": 0.0,
                                                "equity": 0.0, "open_n": 0, "skipped_n": 0,
                                                "source": "live", "kind": "point"}),
    # v201: the admin refresher's tables.
    "quote_currencies": (QuoteCurrencyRepository,
                         {"symbol": "AAPL", "outcome": "known", "checked_at": TS}),
    "market_refresh_queue": (RefreshQueueRepository,
                             {"kind": "quote", "key": "AAPL", "priority": 1, "requested_at": TS}),
    "market_refresh_marks": (RefreshMarkRepository,
                             {"key": "AAPL", "started_at": TS, "expires_at": TS}),
    "refresher_heartbeat": (RefresherHeartbeatRepository,
                            {"key": "refresher", "beat_at": TS, "cadence_s": 60.0,
                             "session": "regular"}),
    # v208: the Benchmark tab's tables.
    "benchmark_bars": (BenchmarkBarRepository,
                       {"symbol": "SPY", "session": "2026-11-04", "source_symbol": "SPY",
                        "final": True, "as_of": TS}),
    "benchmark_refresh": (BenchmarkRefreshRepository,
                          {"symbol": "SPY", "full_refreshed_on": "2026-11-04"}),
    # v207: viewer accounts.
    "admin_users": (AdminUsersRepository, {"username": "probe-user", "password_hash": "h"}),
}

#: Tables with no repository, and why. Anything else must be in CASES.
NOT_REPOSITORY_BACKED = {
    "dropped_doc_fields": "written only by swingbot.core.db.doc_fields inside Alembic revisions",
    "preregistration_verdicts": "write-once (insert_once only; upsert/insert refused); its doc "
                                "round trip is tests/db/test_preregistration_verdicts_repository.py",
    "fx_daily_rates": "composite key (base, account, day), written insert_if_absent only and "
                      "read as promoted columns; its round trip is tests/db/test_v205_fx_daily_rates.py",
    "market_shock_readings": "written only through MarketShockRepository.record with the whole "
                             "reading in doc; its round trip is tests/db/test_market_shock_repository.py",
    "market_shock_state": "single row (id = 1) upserted by MarketShockRepository.record; its "
                          "round trip is tests/db/test_market_shock_repository.py",
    "admin_snapshots": "compare-and-set put(key, doc, inputs, computed_at) only, no upsert/list_all; "
                       "doc is stored whole; its round trip is tests/db/test_v204_admin_snapshots.py",
    "feed_posts": "append-only spoken-headline log written by FeedPostsRepository.insert with "
                  "doc {} and read as promoted columns; tests/db/test_feed_posts_repository.py",
}

#: Tables whose rows need the probe plan first (a foreign key into plans).
NEEDS_PLAN = {"starred_plans", "plan_followers", "plan_notifications"}


def _write(repo, record, conn):
    # Surrogate-keyed tables (append-only) insert; natural keys upsert.
    if repo.key == "id":
        return repo.insert(record, conn=conn)
    return repo.upsert(record, conn=conn)


@pytest.mark.parametrize("table", sorted(CASES))
def test_an_unseen_field_round_trips_unchanged(table, db_conn):
    factory, required = CASES[table]
    if table in NEEDS_PLAN:
        PlanRepository().upsert(dict(PLAN), conn=db_conn)   # its foreign key
    repo = factory()
    assert repo.table.name == table
    _write(repo, {**required, "_v116_probe": PROBE}, db_conn)
    rows = [row for row in repo.list_all(conn=db_conn) if "_v116_probe" in row]
    assert len(rows) == 1
    assert rows[0]["_v116_probe"] == PROBE


def test_every_table_is_covered_or_excused():
    assert set(schema.METADATA.tables) <= set(CASES) | set(NOT_REPOSITORY_BACKED)
