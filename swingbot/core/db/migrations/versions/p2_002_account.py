"""Create account and balance history.

Revision ID: p2_002
Revises: p2_001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from swingbot.core.db.notify import trigger_ddl

revision, down_revision, branch_labels, depends_on = "p2_002", "p2_001", None, None


def _standard():
    return [sa.Column("doc", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("account", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("key", sa.Text, nullable=False, unique=True), *_standard())
    op.create_table("account_balance_history", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False), sa.Column("balance", sa.Numeric, nullable=False), *_standard())
    op.create_index("account_balance_history_ts_idx", "account_balance_history", ["ts"])
    op.execute(trigger_ddl("account", "account"))
    op.execute(trigger_ddl("account_balance_history", "account"))


def downgrade() -> None:
    op.drop_table("account_balance_history")
    op.drop_table("account")
