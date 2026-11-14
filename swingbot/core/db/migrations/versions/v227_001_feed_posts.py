"""v227: feed_posts -- one row per accepted simple-channel post, spoken by the site.

Additive: rollback is this revision's downgrade (drop the trigger, then the
table). Leaving it after a code-only rollback is also safe: older code never
reads feed_posts, and an older admin ignores the unknown `feed` channel
(swingbot/admin/events/db_listener.py logs it at debug and moves on).

Revision ID: v227_001
Revises: v209_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from swingbot.core.db.notify import drop_trigger_ddl, trigger_ddl

revision = "v227_001"
down_revision = "v209_001"   # = python -m alembic heads on the branch at implementation time
branch_labels = None
depends_on = None

# op.execute(trigger_ddl(...)) is non-literal SQL, which scripts/ops/rollback_migrations.py
# cannot read; this states why running older code on this schema is still safe.
ROLLBACK_SAFE = "older code never reads feed_posts; an older admin ignores the unknown feed channel"

_TS = sa.TIMESTAMP(timezone=True)
# Restated rather than read from the events registry: a revision is frozen.
_TABLE = ("feed_posts", "feed")


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    table, channel = _TABLE
    op.create_table(table,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("posted_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("ticker", sa.Text, nullable=True),
        sa.Column("headline", sa.Text, nullable=False),
        *_standard())
    op.create_index("feed_posts_posted_at_idx", table, ["posted_at"])
    op.execute(trigger_ddl(table, channel))


def downgrade() -> None:
    table, _channel = _TABLE
    op.execute(drop_trigger_ddl(table))
    op.drop_index("feed_posts_posted_at_idx", table_name=table)
    op.drop_table(table)
