"""Debts: standalone debt entity, balance snapshots, category link.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "debts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("debt_type", sa.String(30), nullable=False),
        sa.Column(
            "linked_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("manual_balance", sa.Numeric(19, 4), nullable=True),
        sa.Column("interest_rate", sa.Numeric(7, 4), nullable=False),
        sa.Column("minimum_payment", sa.Numeric(19, 4), nullable=False),
        sa.Column("compounding", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("origination_date", sa.Date, nullable=True),
        sa.Column("original_principal", sa.Numeric(19, 4), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "debt_balance_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "debt_id",
            UUID(as_uuid=True),
            sa.ForeignKey("debts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("balance", sa.Numeric(19, 4), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("debt_id", "date", name="uq_debt_snapshot_date"),
    )

    op.add_column(
        "categories",
        sa.Column(
            "linked_debt_id",
            UUID(as_uuid=True),
            sa.ForeignKey("debts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("categories", "linked_debt_id")
    op.drop_table("debt_balance_snapshots")
    op.drop_table("debts")
