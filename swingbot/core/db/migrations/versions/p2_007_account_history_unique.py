"""Make balance-history timestamps idempotent import keys.

Revision ID: p2_007
Revises: p2_006
"""
from alembic import op


revision = "p2_007"
down_revision = "p2_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("account_balance_history_ts_idx", table_name="account_balance_history")
    op.create_unique_constraint(
        "account_balance_history_ts_key", "account_balance_history", ["ts"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "account_balance_history_ts_key", "account_balance_history", type_="unique"
    )
    op.create_index("account_balance_history_ts_idx", "account_balance_history", ["ts"])
