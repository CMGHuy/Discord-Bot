"""create admin state

Revision ID: p3_003
Revises: p3_002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="p3_003"; down_revision="p3_002"; branch_labels=None; depends_on=None
def _std(): return [sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())]
def upgrade():
    op.create_table("ui_preferences", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("owner", sa.Text, nullable=False, unique=True), *_std())
    op.create_table("settings_audit", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False), *_std())
    op.create_index("settings_audit_ts_idx", "settings_audit", ["ts"])
def downgrade(): op.drop_table("settings_audit"); op.drop_table("ui_preferences")
