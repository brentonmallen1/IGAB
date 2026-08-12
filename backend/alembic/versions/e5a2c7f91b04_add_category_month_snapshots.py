"""add category month snapshots

Revision ID: e5a2c7f91b04
Revises: b3f1c8a7d2e9
Create Date: 2026-08-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e5a2c7f91b04"
down_revision: Union[str, Sequence[str], None] = "b3f1c8a7d2e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "category_month_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("assigned", sa.Numeric(19, 4), nullable=False),
        sa.Column("activity", sa.Numeric(19, 4), nullable=False),
        sa.Column("available", sa.Numeric(19, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("category_id", "month", name="uq_snapshot_category_month"),
    )
    op.create_index(
        "ix_snapshot_budget_month", "category_month_snapshots", ["budget_id", "month"]
    )
    op.create_table(
        "budget_snapshot_meta",
        sa.Column(
            "budget_id",
            UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("budget_snapshot_meta")
    op.drop_index("ix_snapshot_budget_month", table_name="category_month_snapshots")
    op.drop_table("category_month_snapshots")
