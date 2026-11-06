"""v205: fx_daily_rates -- one FX rate per (major base, major account, Berlin day).

Additive: rollback is this revision's downgrade; leaving the table after a code
rollback is also safe (the old code never reads it).

Revision ID: v205_001
Revises: v200_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v205_001"
down_revision = "v200_001"   # = python -m alembic heads on the branch at implementation time
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("fx_daily_rates",
        sa.Column("base", sa.Text, primary_key=True),
        sa.Column("account", sa.Text, primary_key=True),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("rate", sa.Float(53), nullable=False),
        sa.Column("bar_date", sa.Date, nullable=False),
        sa.Column("snapped_at", _TS, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        *_standard())


def downgrade() -> None:
    op.drop_table("fx_daily_rates")
