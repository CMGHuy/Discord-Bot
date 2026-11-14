"""v208: equity_samples.open_notional/_approx, benchmark_bars, benchmark_refresh.

Additive: two nullable columns (existing rows stay NULL, no read-time upcasting)
and two new tables. Rollback is this revision's downgrade; leaving them after a
code rollback is also safe (the old code never reads them).

Revision ID: v208_001
Revises: v227_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v208_001"
down_revision = "v227_001"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.add_column("equity_samples", sa.Column("open_notional", sa.Float(53)))
    op.add_column("equity_samples", sa.Column("open_notional_approx", sa.Boolean))
    op.create_table("benchmark_bars",
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("session", sa.Date, primary_key=True),
        sa.Column("close", sa.Float(53)),
        sa.Column("adj_close", sa.Float(53)),
        sa.Column("day_pct", sa.Float(53)),
        sa.Column("source_symbol", sa.Text, nullable=False),
        sa.Column("final", sa.Boolean, nullable=False),
        sa.Column("as_of", _TS, nullable=False),
        *_standard())
    op.create_table("benchmark_refresh",
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("full_refreshed_on", sa.Date, nullable=False),
        *_standard())


def downgrade() -> None:
    op.drop_table("benchmark_refresh")
    op.drop_table("benchmark_bars")
    op.drop_column("equity_samples", "open_notional_approx")
    op.drop_column("equity_samples", "open_notional")
