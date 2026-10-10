"""SQLAlchemy Core table definitions and their promoted-column contracts."""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

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
    sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("queued_at", sa.TIMESTAMP(timezone=True), nullable=False),
    *standard_columns(), sa.Index("manual_close_notify_queued_idx", "queued_at")), ("queued_at",))
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
        "plan_id": "natural key; foreign-key target of starred_plans",
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
    "manual_close_notify": {"queued_at": "manual_close_notify_queued_idx; drain order"},
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
}
