"""dropped_doc_fields: the side table drop_doc_field snapshots into

Revision ID: v116_002
Revises: v116_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v116_002"
down_revision = "v116_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dropped_doc_fields",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("table_name", sa.Text, nullable=False),
        sa.Column("field", sa.Text, nullable=False),
        sa.Column("row_id", sa.BigInteger, nullable=False),
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("table_name", "field", "row_id", name="dropped_doc_fields_row_uq"),
    )


def downgrade() -> None:
    op.drop_table("dropped_doc_fields")
