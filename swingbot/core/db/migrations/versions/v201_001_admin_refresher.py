"""v201: admin market refresher stores -- quote currencies, refresh queue,
in-flight marks, heartbeat -- and market_cache (kind, updated_at).

Additive: rollback is this revision's downgrade; leaving the tables after a
code rollback is also safe (nothing else reads them).

Revision ID: v201_001
Revises: v173_002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v201_001"
down_revision = "v173_002"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("quote_currencies",
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("code", sa.Text),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("checked_at", _TS, nullable=False),
        sa.Column("retry_after", _TS),
        *_standard())
    op.create_table("market_refresh_queue",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("priority", sa.SmallInteger, nullable=False),
        sa.Column("requested_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("taken_at", _TS),
        *_standard())
    op.create_index("market_refresh_queue_pending_uq", "market_refresh_queue",
                    ["kind", "key"], unique=True,
                    postgresql_where=sa.text("taken_at IS NULL"))
    op.create_index("market_refresh_queue_take_idx", "market_refresh_queue",
                    ["taken_at", "priority", "requested_at"])
    op.create_table("market_refresh_marks",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("started_at", _TS, nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("error_at", _TS),
        *_standard())
    op.create_index("market_refresh_marks_updated_idx", "market_refresh_marks", ["updated_at"])
    op.create_table("refresher_heartbeat",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("beat_at", _TS, nullable=False),
        sa.Column("cadence_s", sa.Float(53), nullable=False),
        sa.Column("session", sa.Text, nullable=False),
        sa.Column("cycle_ms", sa.Integer),
        sa.Column("last_error", sa.Text),
        *_standard())
    op.create_index("market_cache_kind_updated_idx", "market_cache", ["kind", "updated_at"])


def downgrade() -> None:
    op.drop_index("market_cache_kind_updated_idx", table_name="market_cache")
    for name in ("refresher_heartbeat", "market_refresh_marks", "market_refresh_queue",
                 "quote_currencies"):
        op.drop_table(name)   # drops each table's own indexes with it
