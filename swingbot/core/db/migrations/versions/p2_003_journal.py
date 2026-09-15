"""Create journal entries.

Revision ID: p2_003
Revises: p2_002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from swingbot.core.db.notify import trigger_ddl

revision, down_revision, branch_labels, depends_on = "p2_003", "p2_002", None, None


def _standard():
    return [sa.Column("doc", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("journal_entries", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("trade_id", sa.Text, nullable=False, unique=True), sa.Column("strategy", sa.Text), sa.Column("outcome", sa.Text), sa.Column("closed_at", sa.TIMESTAMP(timezone=True)), sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False), *_standard())
    op.create_index("journal_entries_closed_idx", "journal_entries", [sa.text("closed_at DESC")])
    op.create_index("journal_entries_doc_gin", "journal_entries", ["doc"], postgresql_using="gin")
    op.execute(trigger_ddl("journal_entries", "journal"))


def downgrade() -> None:
    op.drop_table("journal_entries")
