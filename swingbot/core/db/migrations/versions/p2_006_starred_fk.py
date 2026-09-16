"""Constrain stars to existing plans.

Revision ID: p2_006
Revises: p2_005
"""
from alembic import op

revision = "p2_006"
down_revision = "p2_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM starred_plans s WHERE NOT EXISTS "
               "(SELECT 1 FROM plans p WHERE p.plan_id = s.plan_id)")
    op.create_foreign_key("starred_plans_plan_id_fkey", "starred_plans", "plans",
                          ["plan_id"], ["plan_id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("starred_plans_plan_id_fkey", "starred_plans", type_="foreignkey")
