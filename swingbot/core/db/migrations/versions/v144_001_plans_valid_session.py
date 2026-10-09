"""plans.valid_session: the v144 outlook plan's one NYSE session, indexed

A promote (docs/claude/schema-evolution.md): the column, a backfill from doc for
any row that already carries the field, and the index. The downgrade copies the
column back into doc before dropping it, so no value is lost either way.

Revision ID: v144_001
Revises: v116_002
"""
import sqlalchemy as sa
from alembic import op

revision = "v144_001"
down_revision = "v116_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("valid_session", sa.Text(), nullable=True))
    op.execute("UPDATE plans SET valid_session = doc->>'valid_session' "
               "WHERE doc ? 'valid_session' AND doc->>'valid_session' IS NOT NULL")
    op.create_index("plans_valid_session_idx", "plans", ["valid_session"])


def downgrade() -> None:
    op.execute("UPDATE plans SET doc = jsonb_set(doc, '{valid_session}', to_jsonb(valid_session)) "
               "WHERE valid_session IS NOT NULL")
    op.drop_index("plans_valid_session_idx", table_name="plans")
    op.drop_column("plans", "valid_session")
