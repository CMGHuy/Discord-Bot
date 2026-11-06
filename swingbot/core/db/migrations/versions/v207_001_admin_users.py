"""v207: admin_users -- read-only viewer accounts beside the `.env` admin.

Additive: rollback is redeploying the previous image (the old code never reads
the table, so it can stay). This revision's downgrade drops the table and
every viewer account with it.

Revision ID: v207_001
Revises: v197_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v207_001"
down_revision = "v197_001"
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("admin_users",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("username", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default=sa.text("'viewer'")),
        sa.Column("disabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("credential_version", sa.Integer, nullable=False,
                  server_default=sa.text("1")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", _TS),
        *_standard(),
        sa.CheckConstraint("role IN ('viewer')", name="admin_users_role_ck"))
    op.create_index("admin_users_username_lower_uq", "admin_users",
                    [sa.text("lower(username)")], unique=True)


def downgrade() -> None:
    op.drop_index("admin_users_username_lower_uq", table_name="admin_users")
    op.drop_table("admin_users")
