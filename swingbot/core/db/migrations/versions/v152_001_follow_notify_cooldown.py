"""plan_followers, plan_notifications, notify_prefs, alert_posts (v152 D1-D3)

Four new hybrid tables, no change to an existing one. No NOTIFY trigger: the
SPA streams none of them. The downgrade drops all four; the followers record
and the notification claims go with them (trade taken_by stays in trades.doc).

Revision ID: v152_001
Revises: v144_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v152_001"
down_revision = "v144_001"
branch_labels = None
depends_on = None

_TABLES = ("plan_followers", "plan_notifications", "notify_prefs", "alert_posts")


def _std():
    return [
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def _plan_fk():
    return sa.ForeignKeyConstraint(["plan_id"], ["plans.plan_id"], ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "plan_followers",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("plan_id", sa.Text, nullable=False),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        *_std(),
        _plan_fk(),
        sa.UniqueConstraint("plan_id", "user_id", "kind", name="plan_followers_row_uq"),
    )
    op.create_index("plan_followers_plan_idx", "plan_followers", ["plan_id"])
    op.create_table(
        "plan_notifications",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("plan_id", sa.Text, nullable=False),
        sa.Column("event", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        *_std(),
        _plan_fk(),
        sa.UniqueConstraint("plan_id", "event", name="plan_notifications_claim_uq"),
    )
    op.create_index("plan_notifications_state_idx", "plan_notifications", ["state"])
    op.create_table(
        "notify_prefs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.BigInteger, nullable=False, unique=True),
        *_std(),
    )
    op.create_table(
        "alert_posts",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        *_std(),
    )
    op.create_index("alert_posts_ticker_at_idx", "alert_posts", ["ticker", "at"])


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)    # drops its indexes and constraints with it
