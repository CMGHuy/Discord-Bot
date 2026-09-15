"""Create plans and starred plans.

Revision ID: p2_001
Revises: p1_003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from swingbot.core.db.notify import trigger_ddl

revision, down_revision, branch_labels, depends_on = "p2_001", "p1_003", None, None


def _standard():
    return [sa.Column("doc", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("plans", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("plan_id", sa.Text, nullable=False, unique=True), sa.Column("ticker", sa.Text, nullable=False), sa.Column("strategy", sa.Text, nullable=False), sa.Column("horizon_key", sa.Text, nullable=False), sa.Column("status", sa.Text, nullable=False), sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False), *_standard())
    op.create_index("plans_status_idx", "plans", ["status"])
    op.create_index("plans_ticker_idx", "plans", ["ticker"])
    op.create_index("plans_doc_gin", "plans", ["doc"], postgresql_using="gin")
    op.create_table("starred_plans", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("plan_id", sa.Text, nullable=False, unique=True), *_standard())
    op.execute(trigger_ddl("plans", "trades"))
    op.execute(trigger_ddl("starred_plans", "trades"))


def downgrade() -> None:
    op.drop_table("starred_plans")
    op.drop_table("plans")
