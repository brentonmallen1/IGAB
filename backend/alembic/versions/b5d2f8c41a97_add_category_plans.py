"""add category plans

One table behind the Guide's category planner: named paycheck-by-paycheck
plans, each a JSONB document of header facts and rows (integer cents).

Revision ID: b5d2f8c41a97
Revises: e8c4b6a92f17
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b5d2f8c41a97"
down_revision: Union[str, Sequence[str], None] = "e8c4b6a92f17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "category_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("budget_id", "name", name="uq_category_plan_budget_name"),
    )
    op.create_index("ix_category_plans_budget_id", "category_plans", ["budget_id"])


def downgrade() -> None:
    # Plans are planning scratchpads; the budget's real categories, targets
    # and assignments are untouched by dropping them.
    op.drop_index("ix_category_plans_budget_id", table_name="category_plans")
    op.drop_table("category_plans")
