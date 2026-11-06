"""SQLAlchemy Core table definitions and their promoted-column contracts."""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION, JSONB

from swingbot.core.db.codec import RESERVED_KEYS

METADATA = sa.MetaData()

# Table name -> flat-record fields stored as relational columns.  Every other
# field remains in ``doc`` so new record attributes do not require a schema
# migration.
PROMOTED: dict[str, tuple[str, ...]] = {}


def standard_columns() -> list[sa.Column]:
    """Columns every persisted aggregate carries beyond its own identity."""
    return [
        sa.Column("doc", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def register(table: sa.Table, promoted: Sequence[str]) -> sa.Table:
    """Register and validate a table's promoted flat-record fields."""
    columns = set(table.c.keys())
    missing = [name for name in promoted if name not in columns]
    if missing:
        raise ValueError(f"{table.name}: {missing} not a column on this table")
    clash = RESERVED_KEYS.intersection(promoted)
    if clash:
        raise ValueError(
            f"{table.name}: {sorted(clash)} are infrastructure columns and cannot be promoted"
        )
    PROMOTED[table.name] = tuple(promoted)
    return table


def promoted_for(table_name: str) -> tuple[str, ...]:
    """Return the flat fields persisted as columns for ``table_name``."""
    return PROMOTED[table_name]


def _doc_ok(column: sa.Column) -> bool:
    return (isinstance(column.type, JSONB) and not column.nullable
            and column.server_default is not None)


def contract_violations(table: sa.Table) -> list[str]:
    """What a table breaks of the hybrid contract (docs/claude/schema-evolution.md):
    a `doc JSONB NOT NULL DEFAULT '{}'` and an `updated_at TIMESTAMPTZ NOT NULL`."""
    problems = []
    doc = table.c.get("doc")
    if doc is None:
        problems.append(f"{table.name}: no doc column")
    elif not _doc_ok(doc):
        problems.append(f"{table.name}: doc must be JSONB NOT NULL DEFAULT '{{}}'")
    updated = table.c.get("updated_at")
    if updated is None:
        problems.append(f"{table.name}: no updated_at column")
    elif not getattr(updated.type, "timezone", False) or updated.nullable:
        problems.append(f"{table.name}: updated_at must be TIMESTAMPTZ NOT NULL")
    return problems


trades = register(
    sa.Table(
        "trades", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("trade_id", sa.Text, nullable=False, unique=True),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("strategy", sa.Text, nullable=False),
        sa.Column("horizon", sa.Text, nullable=False),
        sa.Column("direction", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("opened_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("entry", sa.Float(53)),
        sa.Column("stop_loss", sa.Float(53)),
        *standard_columns(),
        sa.Index("trades_ticker_opened_idx", "ticker", sa.text("opened_at DESC")),
        sa.Index("trades_status_idx", "status"),
        sa.Index("trades_doc_gin", "doc", postgresql_using="gin"),
    ),
    ("trade_id", "ticker", "strategy", "horizon", "direction", "status",
     "opened_at", "closed_at", "entry", "stop_loss"),
)

plans = register(
    sa.Table(
        "plans", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("plan_id", sa.Text, nullable=False, unique=True),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("strategy", sa.Text, nullable=False),
        sa.Column("horizon_key", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("valid_session", sa.Text),
        *standard_columns(),
        sa.Index("plans_status_idx", "status"),
        sa.Index("plans_ticker_idx", "ticker"),
        sa.Index("plans_valid_session_idx", "valid_session"),
        sa.Index("plans_doc_gin", "doc", postgresql_using="gin"),
    ),
    ("plan_id", "ticker", "strategy", "horizon_key", "status", "created_at", "valid_session"),
)

starred_plans = register(sa.Table(
    "starred_plans", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("plan_id", sa.Text, sa.ForeignKey("plans.plan_id", ondelete="CASCADE"),
              nullable=False, unique=True), *standard_columns(),
), ("plan_id",))

account = register(sa.Table(
    "account", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("key", sa.Text, nullable=False, unique=True), *standard_columns(),
), ("key",))

account_balance_history = register(sa.Table(
    "account_balance_history", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False, unique=True),
    sa.Column("balance", sa.Float(53), nullable=False), *standard_columns(),
), ("ts", "balance"))

journal_entries = register(sa.Table(
    "journal_entries", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("trade_id", sa.Text, nullable=False, unique=True), sa.Column("strategy", sa.Text),
    sa.Column("outcome", sa.Text), sa.Column("closed_at", sa.TIMESTAMP(timezone=True)),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False), *standard_columns(),
    sa.Index("journal_entries_closed_idx", sa.text("closed_at DESC")),
    sa.Index("journal_entries_doc_gin", "doc", postgresql_using="gin"),
), ("trade_id", "strategy", "outcome", "closed_at", "created_at"))

signal_state = register(sa.Table(
    "signal_state", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("key", sa.Text, nullable=False, unique=True), *standard_columns(),
), ("key",))

watchlist = register(sa.Table(
    "watchlist", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("ticker", sa.Text, nullable=False, unique=True),
    sa.Column("added_at", sa.TIMESTAMP(timezone=True), nullable=False), *standard_columns(),
), ("ticker", "added_at"))

# Part 3 operational state.
runtime_flags = register(sa.Table("runtime_flags", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("name", sa.Text, nullable=False, unique=True),
    sa.Column("set_at", sa.TIMESTAMP(timezone=True), nullable=False), *standard_columns()), ("name", "set_at"))
bot_heartbeat = register(sa.Table("bot_heartbeat", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("key", sa.Text, nullable=False, unique=True),
    sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False), *standard_columns()), ("key", "ts"))
admin_jobs = register(sa.Table("admin_jobs", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("job_id", sa.Text, nullable=False, unique=True),
    sa.Column("kind", sa.Text, nullable=False), sa.Column("status", sa.Text, nullable=False),
    sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False), sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns(), sa.Index("admin_jobs_status_idx", "status")), ("job_id", "kind", "status", "started_at", "finished_at"))
scheduled_jobs = register(sa.Table("scheduled_jobs", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("job", sa.Text, nullable=False, unique=True),
    sa.Column("fired_on", sa.Text, nullable=False), *standard_columns()), ("job", "fired_on"))
ui_preferences = register(sa.Table("ui_preferences", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("owner", sa.Text, nullable=False, unique=True),
    *standard_columns()), ("owner",))
settings_audit = register(sa.Table("settings_audit", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False),
    *standard_columns(), sa.Index("settings_audit_ts_idx", "ts")), ("ts",))
killswitch = register(sa.Table("killswitch", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("key", sa.Text, nullable=False, unique=True),
    sa.Column("engaged", sa.Boolean, nullable=False), sa.Column("engaged_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns()), ("key", "engaged", "engaged_at"))
manual_close_notify = register(sa.Table("manual_close_notify", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("queued_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("event_id", sa.Text, nullable=False),
    sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("lease_token", sa.Text),
    sa.Column("lease_until", sa.TIMESTAMP(timezone=True)),
    sa.Column("delivered_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns(),
    sa.Index("manual_close_notify_queued_idx", "queued_at"),
    sa.Index("manual_close_notify_event_uidx", "event_id", unique=True),
    sa.Index("manual_close_notify_due_idx", "next_attempt_at", "queued_at",
             postgresql_where=sa.text("delivered_at IS NULL")),
    sa.Index("manual_close_notify_delivered_idx", "delivered_at",
             postgresql_where=sa.text("delivered_at IS NOT NULL"))),
    ("queued_at", "event_id", "next_attempt_at", "lease_token", "lease_until", "delivered_at"))
ticker_directory = register(sa.Table("ticker_directory", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("symbol", sa.Text, nullable=False, unique=True),
    sa.Column("name", sa.Text), *standard_columns(), sa.Index("ticker_directory_name_idx", "name")), ("symbol", "name"))
tuning_results = register(sa.Table("tuning_results", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("job_id", sa.Text, nullable=False, unique=True),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False), *standard_columns()), ("job_id", "created_at"))
tuning_proposals = register(sa.Table("tuning_proposals", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("filename", sa.Text, nullable=False, unique=True),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False), *standard_columns(),
    sa.Index("tuning_proposals_created_idx", "created_at")), ("filename", "created_at"))


# v116 Phase 1: the last two files that drove live updates. Ephemeral state --
# nothing is imported, and at the db stage both start empty.
scan_progress = register(sa.Table("scan_progress", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("key", sa.Text, nullable=False, unique=True), *standard_columns()), ("key",))
market_data_state = register(sa.Table("market_data_state", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("key", sa.Text, nullable=False, unique=True), *standard_columns()), ("key",))


# v116 Phase 2: where doc_fields.drop_doc_field keeps what it removed, so the
# revision's downgrade can put it back. Written only inside Alembic revisions.
dropped_doc_fields = register(sa.Table("dropped_doc_fields", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("table_name", sa.Text, nullable=False),
    sa.Column("field", sa.Text, nullable=False),
    sa.Column("row_id", sa.BigInteger, nullable=False),
    *standard_columns(),
    sa.UniqueConstraint("table_name", "field", "row_id", name="dropped_doc_fields_row_uq")),
    ("table_name", "field", "row_id"))


# v152 D1-D3: who follows a plan (Watch / Following), the notify channel's
# one-message-per-(plan, event) claim with its retry state, each Discord
# user's /notify settings, and the scheduled scan's alert-post record the
# per-symbol cooldown reads. Followers and claims cascade with their plan;
# the trade keeps its own denormalised taken_by copy (a doc field).
plan_followers = register(sa.Table(
    "plan_followers", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("plan_id", sa.Text, sa.ForeignKey("plans.plan_id", ondelete="CASCADE"),
              nullable=False),
    sa.Column("user_id", sa.BigInteger, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    *standard_columns(),
    sa.UniqueConstraint("plan_id", "user_id", "kind", name="plan_followers_row_uq"),
    sa.Index("plan_followers_plan_idx", "plan_id"),
), ("plan_id", "user_id", "kind"))

plan_notifications = register(sa.Table(
    "plan_notifications", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("plan_id", sa.Text, sa.ForeignKey("plans.plan_id", ondelete="CASCADE"),
              nullable=False),
    sa.Column("event", sa.Text, nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    *standard_columns(),
    sa.UniqueConstraint("plan_id", "event", name="plan_notifications_claim_uq"),
    sa.Index("plan_notifications_state_idx", "state"),
), ("plan_id", "event", "state"))

notify_prefs = register(sa.Table(
    "notify_prefs", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("user_id", sa.BigInteger, nullable=False, unique=True),
    *standard_columns(),
), ("user_id",))

alert_posts = register(sa.Table(
    "alert_posts", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("ticker", sa.Text, nullable=False),
    sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("outcome", sa.Text, nullable=False),
    *standard_columns(),
    sa.Index("alert_posts_ticker_at_idx", "ticker", "at"),
), ("ticker", "at", "outcome"))


# v147: one row per candidate a live gate (RS, plan rejection, compression) threw away, resolved once
# by the nightly counterfactual resolver. Append-only: only cf_status/resolved_at and the outcome doc
# fields are ever updated, by that resolver; rows are never deleted. No SSE event (not in TABLE_CHANNELS).
gate_rejections = register(sa.Table("gate_rejections", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("ticker", sa.Text, nullable=False),
    sa.Column("gate", sa.Text, nullable=False),
    sa.Column("strategy", sa.Text, nullable=False),
    sa.Column("horizon", sa.Text, nullable=False),
    sa.Column("signal_date", sa.Text, nullable=False),
    sa.Column("cf_status", sa.Text, nullable=False),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("resolved_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns(),
    sa.UniqueConstraint("ticker", "gate", "strategy", "horizon", "signal_date",
                        name="gate_rejections_key_uq"),
    sa.Index("gate_rejections_status_idx", "cf_status")),
    ("ticker", "gate", "strategy", "horizon", "signal_date", "cf_status", "created_at", "resolved_at"))

# v172: raw equity samples behind the Dashboard candle chart. `live` rows are written by the
# trade monitor's recorder (one `point` per 5 minutes in regular hours); `backfill` rows by
# scripts/data/backfill_equity_samples.py (four per session day). Candles are built on request
# (admin/api_v1/equity.py); nothing is pre-aggregated. No SSE event (not in TABLE_CHANNELS).
equity_samples = register(sa.Table("equity_samples", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("realized_balance", sa.Float(53), nullable=False),
    sa.Column("unrealized_pnl", sa.Float(53), nullable=False),
    sa.Column("equity", sa.Float(53), nullable=False),
    sa.Column("open_n", sa.Integer, nullable=False),
    sa.Column("skipped_n", sa.Integer, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("backfill_run", sa.Text),
    *standard_columns(),
    sa.UniqueConstraint("at", "source", "kind", name="equity_samples_at_source_kind_uq"),
    sa.Index("equity_samples_source_at_idx", "source", "at")),
    ("at", "realized_balance", "unrealized_pnl", "equity", "open_n", "skipped_n", "source", "kind",
     "backfill_run"))

# v173: the frozen verdict of a pre-registration, written once by the bot's daily
# check (analytics/override_io.run_daily_check). The primary key is the idempotency
# authority: a second insert on the same ledger_id is impossible. Everything but the
# key, the verdict and its date lives in doc (n, weeks, CI, engine flags, the counted
# rows). No SSE event (not in TABLE_CHANNELS); never updated or deleted by code.
preregistration_verdicts = register(sa.Table("preregistration_verdicts", METADATA,
    sa.Column("ledger_id", sa.Text, primary_key=True),
    sa.Column("verdict", sa.Text, nullable=False),
    sa.Column("recorded_on", sa.Date, nullable=False),
    *standard_columns()),
    ("ledger_id", "verdict", "recorded_on"))

# v201: the admin market refresher's stores. Written by the refresher process
# (swingbot/refresher), read by the admin request door. No SSE trigger: the
# refresher raises `market` itself, once per cycle.
quote_currencies = register(sa.Table("quote_currencies", METADATA,
    sa.Column("symbol", sa.Text, primary_key=True),
    sa.Column("code", sa.Text),
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("checked_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("retry_after", sa.TIMESTAMP(timezone=True)),
    *standard_columns()),
    ("symbol", "code", "outcome", "checked_at", "retry_after"))

# v205: one FX rate per (major base, major account, Berlin day): the last positive
# daily close strictly before that day. Written insert-if-absent by the refresher's
# 08:00 Berlin snap and the one-off backfill (core/marketdata/fx_snap.py); read whole
# by core/marketdata/fx_daily.py. No SSE trigger.
fx_daily_rates = register(sa.Table("fx_daily_rates", METADATA,
    sa.Column("base", sa.Text, primary_key=True),
    sa.Column("account", sa.Text, primary_key=True),
    sa.Column("day", sa.Date, primary_key=True),
    sa.Column("rate", sa.Float(53), nullable=False),
    sa.Column("bar_date", sa.Date, nullable=False),
    sa.Column("snapped_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    *standard_columns()),
    ("base", "account", "day", "rate", "bar_date", "snapped_at", "source"))

market_refresh_queue = register(sa.Table("market_refresh_queue", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("key", sa.Text, nullable=False),
    sa.Column("priority", sa.SmallInteger, nullable=False),
    sa.Column("requested_at", sa.TIMESTAMP(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("taken_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns(),
    sa.Index("market_refresh_queue_pending_uq", "kind", "key", unique=True,
             postgresql_where=sa.text("taken_at IS NULL")),
    sa.Index("market_refresh_queue_take_idx", "taken_at", "priority", "requested_at")),
    ("kind", "key", "priority", "requested_at", "taken_at"))

market_refresh_marks = register(sa.Table("market_refresh_marks", METADATA,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("error", sa.Text),
    sa.Column("error_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns(),
    sa.Index("market_refresh_marks_updated_idx", "updated_at")),
    ("key", "started_at", "expires_at", "error", "error_at"))

refresher_heartbeat = register(sa.Table("refresher_heartbeat", METADATA,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("beat_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("cadence_s", sa.Float(53), nullable=False),
    sa.Column("session", sa.Text, nullable=False),
    sa.Column("cycle_ms", sa.Integer),
    sa.Column("last_error", sa.Text),
    *standard_columns()),
    ("key", "beat_at", "cadence_s", "session", "cycle_ms", "last_error"))

# v204: the admin snapshot pages' stored payloads, one row per key (risk,
# analytics.snapshot, analytics.performance:<ledger>, analytics.equity_curve:<ledger>,
# calendar.pnl:<YYYY-MM>). Written only by the refresher's snapshot worker,
# compare-and-set on computed_at. Read by the admin request door. No SSE trigger:
# the worker raises `market` itself.
admin_snapshots = register(sa.Table("admin_snapshots", METADATA,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("stale_inputs", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("inputs", JSONB, nullable=False),
    *standard_columns(),
    sa.Index("admin_snapshots_updated_idx", "updated_at")),
    ("key", "computed_at", "stale_inputs", "inputs"))


# v171: the shared market-data layer (spec D1/D6/D9). No SSE event; none in TABLE_CHANNELS.
market_cache = register(sa.Table("market_cache", METADATA,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("symbol", sa.Text, nullable=False),
    sa.Column("fetched_at", sa.TIMESTAMP(timezone=True)),
    sa.Column("source", sa.Text),
    sa.Column("lease_holder", sa.Text),
    sa.Column("lease_until", sa.TIMESTAMP(timezone=True)),
    *standard_columns(),
    sa.Index("market_cache_kind_updated_idx", "kind", "updated_at")),
    ("key", "kind", "symbol", "fetched_at", "source", "lease_holder", "lease_until"))

provider_budget = register(sa.Table("provider_budget", METADATA,
    sa.Column("provider", sa.Text, primary_key=True),
    sa.Column("tokens", DOUBLE_PRECISION, nullable=False),
    sa.Column("stamp", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("breaker_failures", sa.Integer, nullable=False, server_default=sa.text("0")),
    sa.Column("breaker_open_until", sa.TIMESTAMP(timezone=True)),
    *standard_columns()),
    ("provider", "tokens", "stamp", "breaker_failures", "breaker_open_until"))

market_fetch_counts = register(sa.Table("market_fetch_counts", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("hour", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("provider", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("asker", sa.Text, nullable=False),
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("n", sa.BigInteger, nullable=False),
    *standard_columns(),
    sa.UniqueConstraint("hour", "provider", "kind", "asker", "outcome",
                        name="market_fetch_counts_key_uq")),
    ("hour", "provider", "kind", "asker", "outcome", "n"))


#: Why each promoted column is a column and not a `doc` field. A promotion
#: costs a migration forever after, so each names what needs it: identity,
#: a foreign key, an index a hot query uses, or a NOT NULL the database must
#: enforce. tests/db/test_schema_contract.py requires exactly one line per
#: PROMOTED entry -- promoting a column means adding its reason here.
PROMOTION_REASONS: dict[str, dict[str, str]] = {
    "trades": {
        "trade_id": "natural key; unique lookup from every command and the admin",
        "ticker": "trades_ticker_opened_idx; per-ticker open-trade checks",
        "strategy": "per-strategy filters in analytics",
        "horizon": "one-trade-per-ticker-and-horizon check",
        "direction": "NOT NULL invariant every consumer relies on",
        "status": "trades_status_idx; open/closed filter on every read",
        "opened_at": "trades_ticker_opened_idx ordering; NOT NULL",
        "closed_at": "closed-trade date ranges in analytics",
        "entry": "numeric column for SQL-side P&L queries",
        "stop_loss": "numeric column for SQL-side risk queries",
    },
    "plans": {
        "plan_id": "natural key; foreign-key target of starred_plans, plan_followers, plan_notifications",
        "ticker": "plans_ticker_idx; per-ticker plan lookup",
        "strategy": "per-strategy plan filters",
        "horizon_key": "per-horizon plan filters",
        "status": "plans_status_idx; open-plan polling every tick",
        "created_at": "age ordering on the Plans screen; NOT NULL",
        "valid_session": "plans_valid_session_idx; the v144 wrap-up and outlook read one session's plans",
    },
    "starred_plans": {"plan_id": "unique key and cascading foreign key into plans"},
    "account": {"key": "singleton key ('config')"},
    "account_balance_history": {
        "ts": "unique key; chronological balance history",
        "balance": "numeric column for the equity curve",
    },
    "journal_entries": {
        "trade_id": "natural key; one entry per trade",
        "strategy": "per-strategy journal filters",
        "outcome": "win/loss filters",
        "closed_at": "journal_entries_closed_idx ordering",
        "created_at": "NOT NULL creation time",
    },
    "signal_state": {"key": "natural key of the confirmation state machine"},
    "watchlist": {
        "ticker": "natural key; one row per ticker",
        "added_at": "NOT NULL insertion time for ordering",
    },
    "runtime_flags": {
        "name": "natural key; one row per flag",
        "set_at": "when the flag was raised; shown by the admin",
    },
    "bot_heartbeat": {"key": "singleton key ('bot')", "ts": "liveness age computed in SQL"},
    "admin_jobs": {
        "job_id": "natural key",
        "kind": "filter by job type",
        "status": "admin_jobs_status_idx; active-job lookup",
        "started_at": "newest-first ordering; NOT NULL",
        "finished_at": "age-based prune of finished jobs",
    },
    "scheduled_jobs": {"job": "natural key", "fired_on": "NOT NULL fire-once-a-day date"},
    "ui_preferences": {"owner": "natural key; one row per user"},
    "settings_audit": {"ts": "settings_audit_ts_idx; newest-first audit list"},
    "killswitch": {
        "key": "singleton key ('global')",
        "engaged": "NOT NULL on/off that every issuance checks",
        "engaged_at": "when it engaged; shown to the partner",
    },
    "manual_close_notify": {
        "queued_at": "manual_close_notify_queued_idx; oldest pending age and ordering",
        "event_id": "manual_close_notify_event_uidx; immutable event deduplication and lookup",
        "next_attempt_at": "manual_close_notify_due_idx; due event selection",
        "lease_token": "fenced completion ownership comparison",
        "lease_until": "expired lease selection and fenced completion expiry",
        "delivered_at": "pending partial index and acknowledged retention index",
    },
    "ticker_directory": {"symbol": "natural key", "name": "ticker_directory_name_idx; name search"},
    "tuning_results": {"job_id": "natural key; one result per job", "created_at": "NOT NULL creation time"},
    "tuning_proposals": {
        "filename": "natural key",
        "created_at": "tuning_proposals_created_idx; newest-first list",
    },
    "scan_progress": {"key": "singleton key ('current')"},
    "market_data_state": {"key": "natural key 'SYMBOL|timeframe'"},
    "dropped_doc_fields": {
        "table_name": "which table a dropped value came from; restore filter",
        "field": "which doc field was dropped; restore filter",
        "row_id": "the source row's id; restore join key",
    },
    "plan_followers": {
        "plan_id": "cascading foreign key into plans; plan_followers_plan_idx lookup by plan",
        "user_id": "part of the plan_followers_row_uq natural key; the Discord user",
        "kind": "part of the natural key; watch vs taken filter",
    },
    "plan_notifications": {
        "plan_id": "cascading foreign key into plans; half of the claim key",
        "event": "other half of plan_notifications_claim_uq, the idempotency claim",
        "state": "plan_notifications_state_idx; the retry sweep's state='pending' filter",
    },
    "notify_prefs": {"user_id": "natural key; one row per Discord user"},
    "alert_posts": {
        "ticker": "alert_posts_ticker_at_idx; the per-ticker cooldown window lookup",
        "at": "alert_posts_ticker_at_idx; window, digest count and prune by time; NOT NULL",
        "outcome": "posted vs suppressed; only posted rows open a cooldown window",
    },
    "gate_rejections": {
        "ticker": "gate_rejections_key_uq; the ON CONFLICT DO NOTHING dedupe key",
        "gate": "gate_rejections_key_uq; the report's per-gate cells",
        "strategy": "gate_rejections_key_uq; scopes the taken arm per strategy",
        "horizon": "gate_rejections_key_uq; one setup on two horizons is two rows",
        "signal_date": "gate_rejections_key_uq; the exact-date signal bar the resolver walks from",
        "cf_status": "gate_rejections_status_idx; the resolver's WHERE cf_status = 'pending'",
        "created_at": "NOT NULL write time; resolver due order and the report's live window",
        "resolved_at": "when the outcome was filled once; NULL while pending",
    },
    "market_cache": {
        "key": "natural key; the batched read's WHERE key = ANY(:keys) and every upsert's conflict target",
        "kind": "NOT NULL data kind; the report and pruning scope rows by it",
        "symbol": "NOT NULL symbol the entry belongs to; per-symbol lookups and pruning",
        "fetched_at": "freshness compared against each asker's max age; NULL on a lease-only row",
        "source": "provider that produced the value; the report's per-provider split",
        "lease_holder": "single-flight claim compared in the lease UPDATE's WHERE and the release",
        "lease_until": "single-flight claim compared in the lease UPDATE's WHERE",
    },
    "provider_budget": {
        "provider": "natural key; one shared token bucket and breaker per provider",
        "tokens": "atomic refill-and-take arithmetic in one UPDATE",
        "stamp": "elapsed-time refill computed in the same UPDATE; NOT NULL",
        "breaker_failures": "increment-and-compare in the breaker upsert",
        "breaker_open_until": "open window set in the breaker upsert's CASE; NULL when closed",
    },
    "market_fetch_counts": {
        "hour": "market_fetch_counts_key_uq and the report's time range",
        "provider": "market_fetch_counts_key_uq; the report's per-provider cells",
        "kind": "market_fetch_counts_key_uq; the report's per-kind cells",
        "asker": "market_fetch_counts_key_uq; the report's per-asker cells",
        "outcome": "market_fetch_counts_key_uq; the report's per-outcome cells",
        "n": "upsert increment in SQL",
    },
    "equity_samples": {
        "at": "equity_samples_at_source_kind_uq and equity_samples_source_at_idx; the bucket time",
        "realized_balance": "NOT NULL money the realized basis and --recompute-realized rewrite",
        "unrealized_pnl": "NOT NULL measured money; kept when --recompute-realized rewrites the rest",
        "equity": "NOT NULL money every mark-to-market candle's O/H/L/C is read from",
        "open_n": "NOT NULL count of positions priced into the sample",
        "skipped_n": "NOT NULL count of positions left out; the candle's skipped note",
        "source": "equity_samples_at_source_kind_uq and the range index; live vs backfill filter",
        "kind": "equity_samples_at_source_kind_uq; point vs day_high/day_low, o/c read points only",
        "backfill_run": "names the run and bar date a backfill row was built from; NULL on live rows",
    },
    "preregistration_verdicts": {
        "ledger_id": "primary key: one row per pre-registration, so a second insert is impossible",
        "verdict": "NOT NULL frozen outcome",
        "recorded_on": "NOT NULL date the verdict was recorded",
    },
    "quote_currencies": {
        "symbol": "primary key: one quote-currency answer per symbol",
        "code": "the currency code the admin converts by; NULL until known",
        "outcome": "NOT NULL known/unknown answer the FX job branches on",
        "checked_at": "NOT NULL time of the last lookup; the FX job's staleness test",
        "retry_after": "the FX job's backoff WHERE for an unknown answer; NULL when known",
    },
    "fx_daily_rates": {
        "base": "primary key (base, account, day): one rate per major-code pair per Berlin day",
        "account": "primary key (base, account, day): the major account currency converted into",
        "day": "primary key: the Berlin calendar day the rate serves; fx_daily.lookup's sort key",
        "rate": "NOT NULL multiplier fx_daily.lookup returns; never 1.0 for a missing pair",
        "bar_date": "NOT NULL date of the frame bar the rate came from; the FALLBACK_DAYS test",
        "snapped_at": "NOT NULL write time; max(snapped_at) is half of the memo's version key",
        "source": "NOT NULL snap/backfill provenance, checked after the deploy backfill",
    },
    "market_refresh_queue": {
        "kind": "market_refresh_queue_pending_uq: one pending request per (kind, key)",
        "key": "market_refresh_queue_pending_uq: one pending request per (kind, key)",
        "priority": "market_refresh_queue_take_idx: the take order, foreground before background",
        "requested_at": "market_refresh_queue_take_idx: FIFO within a priority",
        "taken_at": "pending-vs-taken split in the partial unique index and the take index",
    },
    "market_refresh_marks": {
        "key": "primary key: one in-flight mark per refreshed key",
        "started_at": "NOT NULL time the refresh began; how long it has run",
        "expires_at": "in-flight test (expires_at > now) in every active() read",
        "error": "last refresh failure shown to the admin; NULL on success",
        "error_at": "when that failure happened; NULL on success",
    },
    "refresher_heartbeat": {
        "key": "primary key: one heartbeat row per refresher process",
        "beat_at": "stalled test (age > 3 x cadence) in /system/health and /market/updates",
        "cadence_s": "NOT NULL expected seconds between beats; the stalled test's multiplier",
        "session": "NOT NULL market session the cadence was chosen for",
        "cycle_ms": "duration of the last cycle in /system/health; NULL before the first",
        "last_error": "last cycle failure in /system/health; NULL when clean",
    },
    "admin_snapshots": {
        "key": "primary key; one row per snapshot key, so the table never grows with time",
        "computed_at": "the compare-and-set WHERE in put (newer computed_at wins) and the "
                       "closed-market stale rule",
        "stale_inputs": "bars older than the last completed session; read by /market/updates "
                        "without the doc",
        "inputs": "recorded inputs (quotes, FX, bar fingerprints, thresholds, code version), "
                  "apart from doc",
    },
}
