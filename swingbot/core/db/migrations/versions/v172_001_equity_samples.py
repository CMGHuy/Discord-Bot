"""equity_samples: raw equity samples for the Dashboard candle chart (v172).

Additive: rollback is this revision's downgrade (drop the table); leaving
the table in place after a code rollback is also safe.

Revision ID: v172_001
Revises: v146_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v172_001"
down_revision = "v146_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equity_samples",
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
        sa.Column("doc", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("at", "source", "kind", name="equity_samples_at_source_kind_uq"),
    )
    op.create_index("equity_samples_source_at_idx", "equity_samples", ["source", "at"])


def downgrade() -> None:
    op.drop_index("equity_samples_source_at_idx", table_name="equity_samples")
    op.drop_table("equity_samples")
