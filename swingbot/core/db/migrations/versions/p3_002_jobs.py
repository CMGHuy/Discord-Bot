"""create operational jobs

Revision ID: p3_002
Revises: p3_001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="p3_002"; down_revision="p3_001"; branch_labels=None; depends_on=None
def _std(): return [sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())]
def upgrade():
    op.create_table("admin_jobs", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("job_id", sa.Text, nullable=False, unique=True), sa.Column("kind", sa.Text, nullable=False), sa.Column("status", sa.Text, nullable=False), sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False), sa.Column("finished_at", sa.TIMESTAMP(timezone=True)), *_std())
    op.create_index("admin_jobs_status_idx", "admin_jobs", ["status"])
    op.create_table("scheduled_jobs", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("job", sa.Text, nullable=False, unique=True), sa.Column("fired_on", sa.Text, nullable=False), *_std())
def downgrade(): op.drop_table("scheduled_jobs"); op.drop_table("admin_jobs")
