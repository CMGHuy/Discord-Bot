"""Create watchlist.

Revision ID: p2_005
Revises: p2_004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from swingbot.core.db.notify import trigger_ddl

revision, down_revision, branch_labels, depends_on = "p2_005", "p2_004", None, None


def _standard():
    return [sa.Column("doc", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("watchlist", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("ticker", sa.Text, nullable=False, unique=True), sa.Column("added_at", sa.TIMESTAMP(timezone=True), nullable=False), *_standard())
    op.execute(trigger_ddl("watchlist", "watchlist"))


def downgrade() -> None:
    op.drop_table("watchlist")
