"""install NOTIFY triggers for every event-raising table

Idempotent sweep over events.TABLE_CHANNELS: each trigger is dropped if present
and recreated, so tables that already carry one (p1_003, p2_001..p2_005) are
re-asserted rather than duplicated.

Revision ID: p3_007
Revises: p6_001
"""
import sqlalchemy as sa
from alembic import op

from swingbot.core.db.events import TABLE_CHANNELS
from swingbot.core.db.notify import trigger_ddl, trigger_name

revision = "p3_007"
down_revision = "p6_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table, channel in TABLE_CHANNELS.items():
        if table not in existing:
            continue
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name(table)} ON {table}")
        op.execute(trigger_ddl(table, channel))


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in TABLE_CHANNELS:
        if table in existing:
            op.execute(f"DROP TRIGGER IF EXISTS {trigger_name(table)} ON {table}")
