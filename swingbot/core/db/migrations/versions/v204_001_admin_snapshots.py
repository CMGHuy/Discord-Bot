"""v204: admin_snapshots -- stored Risk/Analytics/Calendar/sparkline payloads.

Additive. Rollback is this revision's downgrade. Leaving the table after a code
rollback is also safe: only the snapshot worker and the admin door read it.

Revision ID: v204_001
Revises: v207_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v204_001"
down_revision = "v207_001"  # = python -m alembic heads on main when merged (2026-11-06)
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table("admin_snapshots",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("computed_at", _TS, nullable=False),
        sa.Column("stale_inputs", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("inputs", postgresql.JSONB(), nullable=False),
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()))
    op.create_index("admin_snapshots_updated_idx", "admin_snapshots", ["updated_at"])


def downgrade() -> None:
    op.drop_index("admin_snapshots_updated_idx", table_name="admin_snapshots")
    op.drop_table("admin_snapshots")
