"""create killswitch and manual close queue

Revision ID: p3_004
Revises: p3_003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="p3_004"; down_revision="p3_003"; branch_labels=None; depends_on=None
def _std(): return [sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())]
def upgrade():
    op.create_table("killswitch", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("key", sa.Text, nullable=False, unique=True), sa.Column("engaged", sa.Boolean, nullable=False), sa.Column("engaged_at", sa.TIMESTAMP(timezone=True)), *_std())
    op.create_table("manual_close_notify", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("queued_at", sa.TIMESTAMP(timezone=True), nullable=False), *_std())
    op.create_index("manual_close_notify_queued_idx", "manual_close_notify", ["queued_at"])
def downgrade(): op.drop_table("manual_close_notify"); op.drop_table("killswitch")
