"""v204: admin_snapshots -- stored Risk/Analytics/Calendar/sparkline payloads.

Additive. Rollback is this revision's downgrade (`alembic downgrade v207_001`,
run from the v204 image before redeploying an older one): a pre-v204 image does
not know this revision stamp, so deploy.sh aborts on it (DEPLOY_HETZNER.md
§ v204). The table itself is harmless to leave; the stamp is not.

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
