"""create tuning artifacts

Revision ID: p3_006
Revises: p3_005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="p3_006"; down_revision="p3_005"; branch_labels=None; depends_on=None
def _std(): return [sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())]
def upgrade():
    op.create_table("tuning_results", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("job_id", sa.Text, nullable=False, unique=True), sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False), *_std())
    op.create_table("tuning_proposals", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("filename", sa.Text, nullable=False, unique=True), sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False), *_std())
    op.create_index("tuning_proposals_created_idx", "tuning_proposals", ["created_at"])
def downgrade(): op.drop_table("tuning_proposals"); op.drop_table("tuning_results")
