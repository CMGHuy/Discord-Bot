"""Baseline revision: intentionally empty root for the migration graph."""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = "p1_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
