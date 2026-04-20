"""fix ynab inflow category group mapping

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-19 00:00:00.000000

Move transactions and categories from the incorrectly imported "Inflow" category
group to the system "Income" group, then soft-delete the "Inflow" group.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import uuid

    # Create the system "Income" category group for budgets that have "Inflow"
    # but no system Income group (budgets created via YNAB import bypass normal setup)
    op.execute(f"""
        INSERT INTO category_groups (id, budget_id, name, sort_order, is_hidden, is_system, is_deleted, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            inflow.budget_id,
            'Income',
            -1,
            FALSE,
            TRUE,
            FALSE,
            NOW(),
            NOW()
        FROM category_groups inflow
        WHERE inflow.name = 'Inflow'
          AND inflow.is_system = FALSE
          AND inflow.is_deleted = FALSE
          AND NOT EXISTS (
            SELECT 1 FROM category_groups existing
            WHERE existing.budget_id = inflow.budget_id
              AND existing.name = 'Income'
              AND existing.is_system = TRUE
              AND existing.is_deleted = FALSE
          )
    """)

    # Move categories from "Inflow" group to the system "Income" group
    op.execute("""
        UPDATE categories
        SET category_group_id = (
            SELECT income.id
            FROM category_groups income
            WHERE income.budget_id = categories.budget_id
              AND income.name = 'Income'
              AND income.is_system = TRUE
              AND income.is_deleted = FALSE
        )
        WHERE category_group_id IN (
            SELECT inflow.id
            FROM category_groups inflow
            WHERE inflow.name = 'Inflow'
              AND inflow.is_system = FALSE
              AND inflow.is_deleted = FALSE
        )
    """)

    # Soft-delete the now-empty "Inflow" category group
    op.execute("""
        UPDATE category_groups
        SET is_deleted = TRUE
        WHERE name = 'Inflow'
          AND is_system = FALSE
          AND is_deleted = FALSE
    """)


def downgrade() -> None:
    pass
