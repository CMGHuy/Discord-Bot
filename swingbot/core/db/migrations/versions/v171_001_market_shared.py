"""market_cache, provider_budget, market_fetch_counts: the v171 shared market-data layer

One cache row per key (value plus the single-flight lease), one token bucket and
breaker per provider shared by every process, and hourly fetch counts per
(provider, kind, asker, outcome). A new set of tables, so the downgrade drops them whole.

Revision ID: v171_001
Revises: v172_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v171_001"
down_revision = "v172_001"
branch_labels = None
depends_on = None


def _standard() -> list[sa.Column]:
    return [
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "market_cache",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("lease_holder", sa.Text, nullable=True),
        sa.Column("lease_until", sa.TIMESTAMP(timezone=True), nullable=True),
        *_standard(),
    )
    op.create_table(
        "provider_budget",
        sa.Column("provider", sa.Text, primary_key=True),
        sa.Column("tokens", postgresql.DOUBLE_PRECISION(), nullable=False),
        sa.Column("stamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("breaker_failures", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("breaker_open_until", sa.TIMESTAMP(timezone=True), nullable=True),
        *_standard(),
    )
    op.create_table(
        "market_fetch_counts",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("hour", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("asker", sa.Text, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("n", sa.BigInteger, nullable=False),
        *_standard(),
        sa.UniqueConstraint("hour", "provider", "kind", "asker", "outcome",
                            name="market_fetch_counts_key_uq"),
    )


def downgrade() -> None:
    op.drop_table("market_fetch_counts")
    op.drop_table("provider_budget")
    op.drop_table("market_cache")
