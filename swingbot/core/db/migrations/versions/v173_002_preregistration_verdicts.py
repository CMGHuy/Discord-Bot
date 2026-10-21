"""preregistration_verdicts: the frozen verdict of a pre-registration (v173).

Written once by the bot's daily check (analytics/override_io.run_daily_check);
the primary key ledger_id makes a second insert impossible. Additive: rollback
is this revision's downgrade (drop the table); leaving the table in place after
a code rollback is also safe. A verdict row is the frozen record: print it with
`execution_fidelity_report.py --production --mirror-row` before any downgrade.

Revision ID: v173_002
Revises: v173_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v173_002"
down_revision = "v173_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preregistration_verdicts",
        sa.Column("ledger_id", sa.Text, primary_key=True),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("recorded_on", sa.Date, nullable=False),
        sa.Column("doc", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("preregistration_verdicts")
