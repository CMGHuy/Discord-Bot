"""v209: market_shock_readings and market_shock_state -- the shock detector's log
and its single current-state row.

Additive: rollback is this revision's downgrade (drop both tables); leaving them
after a code rollback is also safe (older code never reads them). An image-only
rollback to an older image must run `alembic downgrade v204_001` from this image
first (docs/deploy/DEPLOY_HETZNER.md).

Revision ID: v209_001
Revises: v204_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v209_001"
down_revision = "v204_001"   # = python -m alembic heads on the branch at implementation time
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_HEADLINES = ("breadth_frac", "breadth_speed", "spy_atr_move", "qqq_atr_move",
              "vix_level", "vix_chg_pct", "vix_off_high_pct")


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("market_shock_readings",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("as_of", _TS, nullable=False),
        sa.Column("session_date", sa.Date, nullable=False),
        sa.Column("state_after", sa.Text, nullable=False),
        *[sa.Column(name, sa.Float(53)) for name in _HEADLINES],
        sa.Column("sectors_down", sa.Integer, nullable=False),
        sa.Column("sectors_total", sa.Integer, nullable=False),
        sa.Column("n_names", sa.Integer, nullable=False),
        sa.Column("insufficient", sa.Boolean, nullable=False),
        *_standard())
    op.create_index("market_shock_readings_as_of_idx", "market_shock_readings", ["as_of"])
    op.create_table("market_shock_state",
        sa.Column("id", sa.SmallInteger, primary_key=True, autoincrement=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("since", _TS),
        sa.Column("session_date", sa.Date),
        sa.Column("vix_session_high", sa.Float(53)),
        sa.Column("last_reading_id", sa.BigInteger,
                  sa.ForeignKey("market_shock_readings.id", ondelete="SET NULL")),
        sa.Column("last_notice_at", _TS),
        *_standard(),
        sa.CheckConstraint("id = 1", name="market_shock_state_single_row"))


def downgrade() -> None:
    op.drop_table("market_shock_state")
    op.drop_index("market_shock_readings_as_of_idx", table_name="market_shock_readings")
    op.drop_table("market_shock_readings")
