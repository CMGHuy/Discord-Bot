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
