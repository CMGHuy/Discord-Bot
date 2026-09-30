"""Store trade prices and balances as double precision.

An unbounded ``numeric`` column round-trips a Python float through a decimal
conversion that kept only ~14 significant digits, so ``entry``/``stop_loss``
came back as 427.55741222224 for a source value of 427.5574122222405 and
parity failed on every trade. The JSON stores hold floats and analytics must
be numerically identical, so the columns are ``double precision``.

Revision ID: p6_001
Revises: p6_000
"""
import sqlalchemy as sa
from alembic import op

revision = "p6_001"
down_revision = "p6_000"
branch_labels = None
depends_on = None

_COLUMNS = (("trades", "entry"), ("trades", "stop_loss"),
            ("account_balance_history", "balance"))


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(table, column, type_=sa.Float(53),
                        postgresql_using=f"{column}::double precision")


def downgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(table, column, type_=sa.Numeric(),
                        postgresql_using=f"{column}::numeric")
