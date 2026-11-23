"""v239: market_regime_days -- the bear-regime engine's one write-once row per session.

Additive: rollback is this revision's downgrade (drop the table); leaving it
after a code rollback is also safe (older code never reads it). An image-only
rollback to an older image must run `alembic downgrade v228_001` from this image
first (docs/deploy/DEPLOY_HETZNER.md § v239).

Revision ID: v239_001
Revises: v228_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v239_001"
down_revision = "v228_001"   # = python -m alembic heads on the branch at implementation time
branch_labels = None
ROLLBACK_SAFE = "Older code does not read or write market_regime_days."
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_FLOATS = ("spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20", "spy_high_prev",
           "vix_close", "vix_max5")


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("market_regime_days",
        sa.Column("session_date", sa.Date, primary_key=True),
        sa.Column("last_bar_date", sa.Date),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("stress", sa.Boolean),
        sa.Column("pullback_trigger", sa.Boolean, nullable=False),
        sa.Column("pullback_reason", sa.Text),
        *[sa.Column(name, sa.Float(53)) for name in _FLOATS],
        sa.Column("spy_provider", sa.Text),
        sa.Column("vix_provider", sa.Text),
        sa.Column("computed_at", _TS, nullable=False),
        *_standard(),
        sa.CheckConstraint("state IN ('BEAR', 'CORRECTION', 'NORMAL', 'UNKNOWN')",
                           name="market_regime_days_state"))


def downgrade() -> None:
    op.drop_table("market_regime_days")
