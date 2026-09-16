"""create runtime flags and bot heartbeat

Revision ID: p3_001
Revises: p2_006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "p3_001"
down_revision = "p2_006"
branch_labels = None
depends_on = None


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                      server_default=sa.func.now())]


def upgrade():
    op.create_table("runtime_flags", sa.Column("id", sa.BigInteger, primary_key=True),
                    sa.Column("name", sa.Text, nullable=False, unique=True),
                    sa.Column("set_at", sa.TIMESTAMP(timezone=True), nullable=False), *_standard())
    op.create_table("bot_heartbeat", sa.Column("id", sa.BigInteger, primary_key=True),
                    sa.Column("key", sa.Text, nullable=False, unique=True),
                    sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False), *_standard())


def downgrade():
    op.drop_table("bot_heartbeat")
    op.drop_table("runtime_flags")
