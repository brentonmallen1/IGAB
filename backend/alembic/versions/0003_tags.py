"""Tags for categories and payees.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYSTEM_TAGS = [
    ("subscription", "Subscription", "purple"),
    ("savings", "Savings", "green"),
    ("long_term_expense", "Long-term expense", "teal"),
]


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("system_key", sa.String(30), nullable=True),
        sa.Column("color_slot", sa.String(20), nullable=True),
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
        sa.UniqueConstraint("budget_id", "name", name="uq_tag_budget_name"),
        sa.UniqueConstraint("budget_id", "system_key", name="uq_tag_budget_system_key"),
    )

    op.create_table(
        "category_tags",
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "payee_tags",
        sa.Column(
            "payee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("payees.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # Seed system tags for all existing budgets
    conn = op.get_bind()
    budgets = conn.execute(sa.text("SELECT id FROM budgets")).fetchall()
    for (budget_id,) in budgets:
        for system_key, name, color_slot in SYSTEM_TAGS:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO tags (id, budget_id, name, system_key, color_slot, is_deleted)
                    VALUES (gen_random_uuid(), :budget_id, :name, :system_key, :color_slot, false)
                    """
                ),
                {"budget_id": budget_id, "name": name, "system_key": system_key, "color_slot": color_slot},
            )


def downgrade() -> None:
    op.drop_table("payee_tags")
    op.drop_table("category_tags")
    op.drop_table("tags")
