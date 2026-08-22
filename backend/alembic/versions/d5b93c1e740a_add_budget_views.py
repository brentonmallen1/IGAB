"""add budget views

Revision ID: d5b93c1e740a
Revises: c4f8a2e91d07
Create Date: 2026-08-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5b93c1e740a"
down_revision: Union[str, Sequence[str], None] = "c4f8a2e91d07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A view is a second arrangement of the same categories.

    Distinct from budget_filters (renamed in c4f8a2e91d07), which only narrows
    the set. A view regroups it, so the same categories can be read as
    need/want/save without cloning the budget. The default arrangement stays in
    category_groups and is never edited by a view.
    """
    op.create_table(
        "budget_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("budget_id", "name", name="uq_budget_view_budget_name"),
    )
    op.create_index("ix_budget_views_budget_id", "budget_views", ["budget_id"])

    op.create_table(
        "budget_view_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("view_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["view_id"], ["budget_views.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("view_id", "name", name="uq_budget_view_group_name"),
    )
    op.create_index("ix_budget_view_groups_view_id", "budget_view_groups", ["view_id"])

    op.create_table(
        "budget_view_placements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("view_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        # SET NULL, not CASCADE: deleting a group must leave its categories in
        # the view (under Unassigned), never silently drop them from it.
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["view_id"], ["budget_views.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["budget_view_groups.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("view_id", "category_id", name="uq_budget_view_placement"),
    )
    op.create_index("ix_budget_view_placements_view_id", "budget_view_placements", ["view_id"])
    op.create_index(
        "ix_budget_view_placements_category_id", "budget_view_placements", ["category_id"]
    )
    op.create_index("ix_budget_view_placements_group_id", "budget_view_placements", ["group_id"])


def downgrade() -> None:
    op.drop_table("budget_view_placements")
    op.drop_table("budget_view_groups")
    op.drop_table("budget_views")
