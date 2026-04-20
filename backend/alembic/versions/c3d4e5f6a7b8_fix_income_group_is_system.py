"""fix income category groups missing is_system flag

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-19 00:00:00.000000

The YNAB importer created "Income" category groups without is_system=TRUE
for budgets where it had already mapped "Inflow" → "Income" before the
b2c3d4e5f6a7 migration ran. This marks all non-deleted "Income" groups
as system groups so they are correctly excluded from TBA calculation.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE category_groups
        SET is_system = TRUE
        WHERE name = 'Income'
          AND is_deleted = FALSE
          AND is_system = FALSE
    """)


def downgrade() -> None:
    pass
