"""Install shared statement-level PostgreSQL notifications.

Revision ID: p1_003
Revises: p1_002
"""
from alembic import op

from swingbot.core.db.notify import NOTIFY_FUNCTION_SQL, drop_trigger_ddl, trigger_ddl

revision = "p1_003"
down_revision = "p1_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(NOTIFY_FUNCTION_SQL)
    op.execute(trigger_ddl("trades", "trades"))


def downgrade() -> None:
    op.execute(drop_trigger_ddl("trades"))
    op.execute("DROP FUNCTION IF EXISTS swingbot_notify()")
