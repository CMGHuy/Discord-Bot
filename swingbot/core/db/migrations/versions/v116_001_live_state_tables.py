"""scan_progress and market_data_state, with their NOTIFY triggers

Revision ID: v116_001
Revises: p3_007
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from swingbot.core.db.notify import drop_trigger_ddl, trigger_ddl

revision = "v116_001"
down_revision = "p3_007"
branch_labels = None
depends_on = None

# Restated rather than read from events.TABLE_CHANNELS: a revision is frozen
# at the moment it was written, and a later edit to the map must not change
# what this revision did.
_TABLES = (("scan_progress", "scan"), ("market_data_state", "watchlist"))


def _std():
    return [
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def upgrade() -> None:
    for table, channel in _TABLES:
        op.create_table(table, sa.Column("id", sa.BigInteger, primary_key=True),
                        sa.Column("key", sa.Text, nullable=False, unique=True), *_std())
        op.execute(trigger_ddl(table, channel))


def downgrade() -> None:
    for table, _channel in reversed(_TABLES):
        op.execute(drop_trigger_ddl(table))
        op.drop_table(table)
