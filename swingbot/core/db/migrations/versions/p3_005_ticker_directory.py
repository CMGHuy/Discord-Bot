"""create ticker directory

Revision ID: p3_005
Revises: p3_004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="p3_005"; down_revision="p3_004"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("ticker_directory", sa.Column("id", sa.BigInteger, primary_key=True), sa.Column("symbol", sa.Text, nullable=False, unique=True), sa.Column("name", sa.Text), sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ticker_directory_name_idx", "ticker_directory", ["name"])
def downgrade(): op.drop_table("ticker_directory")
