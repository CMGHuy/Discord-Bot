"""Create the initial normalized trades table.

Revision ID: p1_002
Revises: p1_001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "p1_002"
down_revision = "p1_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trades",
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
        sa.Column("doc", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.execute("CREATE INDEX trades_ticker_opened_idx ON trades (ticker, opened_at DESC)")
    op.create_index("trades_status_idx", "trades", ["status"])
    op.create_index("trades_doc_gin", "trades", ["doc"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_table("trades")
