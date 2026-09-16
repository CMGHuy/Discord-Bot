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
        sa.Column("entry", sa.Numeric),
        sa.Column("stop_loss", sa.Numeric),
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
        *standard_columns(),
        sa.Index("plans_status_idx", "status"),
        sa.Index("plans_ticker_idx", "ticker"),
        sa.Index("plans_doc_gin", "doc", postgresql_using="gin"),
    ),
    ("plan_id", "ticker", "strategy", "horizon_key", "status", "created_at"),
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
    sa.Column("balance", sa.Numeric, nullable=False), *standard_columns(),
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
