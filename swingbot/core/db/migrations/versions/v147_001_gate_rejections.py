"""gate_rejections: the v147 live gate-counterfactual store

One row per candidate the RS, plan-rejection or compression gate threw away on
the live scan; the nightly resolver fills its outcome once. A new table, so the
downgrade drops it whole (no doc field to preserve elsewhere).

Revision ID: v147_001
Revises: v152_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v147_001"
down_revision = "v152_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gate_rejections",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("gate", sa.Text, nullable=False),
        sa.Column("strategy", sa.Text, nullable=False),
        sa.Column("horizon", sa.Text, nullable=False),
        sa.Column("signal_date", sa.Text, nullable=False),
        sa.Column("cf_status", sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("ticker", "gate", "strategy", "horizon", "signal_date",
                            name="gate_rejections_key_uq"),
    )
    op.create_index("gate_rejections_status_idx", "gate_rejections", ["cf_status"])


def downgrade() -> None:
    op.drop_index("gate_rejections_status_idx", table_name="gate_rejections")
    op.drop_table("gate_rejections")
