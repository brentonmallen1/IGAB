"""wishlist

The Guide's wishlist: a keyed, protected category group (`category_groups.
system_key`, the way system tags work — NOT `is_system`, which means the
Income arrangement), projects that group wishes, and the wishes themselves.

Revision ID: b4e7c2d91a56
Revises: c3e7a92d5f18
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4e7c2d91a56"
down_revision: Union[str, Sequence[str], None] = "c3e7a92d5f18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("category_groups", sa.Column("system_key", sa.String(30), nullable=True))
    op.create_unique_constraint(
        "uq_category_group_budget_system_key", "category_groups", ["budget_id", "system_key"]
    )

    op.create_table(
        "wishlist_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wishlist_projects_budget_id", "wishlist_projects", ["budget_id"])
    op.create_index("ix_wishlist_projects_category_id", "wishlist_projects", ["category_id"])

    op.create_table(
        "wishlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wishlist_projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cost", sa.Numeric(19, 4), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("owns_envelope", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("cooling_until", sa.Date(), nullable=True),
        sa.Column("last_affirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wishlist_items_budget_id", "wishlist_items", ["budget_id"])
    op.create_index("ix_wishlist_items_project_id", "wishlist_items", ["project_id"])
    op.create_index("ix_wishlist_items_category_id", "wishlist_items", ["category_id"])


def downgrade() -> None:
    # Wishes are intent, not money: the envelopes they pointed at, and every
    # transaction in them, stay exactly as they were.
    op.drop_index("ix_wishlist_items_category_id", table_name="wishlist_items")
    op.drop_index("ix_wishlist_items_project_id", table_name="wishlist_items")
    op.drop_index("ix_wishlist_items_budget_id", table_name="wishlist_items")
    op.drop_table("wishlist_items")
    op.drop_index("ix_wishlist_projects_category_id", table_name="wishlist_projects")
    op.drop_index("ix_wishlist_projects_budget_id", table_name="wishlist_projects")
    op.drop_table("wishlist_projects")
    op.drop_constraint("uq_category_group_budget_system_key", "category_groups", type_="unique")
    op.drop_column("category_groups", "system_key")
