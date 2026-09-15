"""Create signal state.

Revision ID: p2_004
Revises: p2_003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from swingbot.core.db.notify import trigger_ddl

revision, down_revision, branch_labels, depends_on = "p2_004", "p2_003", None, None


def _standard():
    return [sa.Column("doc", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("signal_state", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("key", sa.Text, nullable=False, unique=True), *_standard())
    op.execute(trigger_ddl("signal_state", "account"))


def downgrade() -> None:
    op.drop_table("signal_state")
