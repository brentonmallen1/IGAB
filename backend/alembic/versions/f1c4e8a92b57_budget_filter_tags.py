"""budget filters can name tags

A saved filter was a frozen list of category ids. A household that tags its
essentials wants a filter that follows the tag: tag a new category Essential
and it appears; untag it and it leaves. `budget_filter_tags` is that axis —
any category carrying one of the filter's tags is in it, in addition to the
categories named outright. The effective set is resolved on the server
(`BudgetFilterRepository.effective_category_ids`) so the budget page and a
report handed a filter_id read the same rule.

Revision ID: f1c4e8a92b57
Revises: e3b9c7d24a61
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "f1c4e8a92b57"
down_revision: str | Sequence[str] | None = "e3b9c7d24a61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budget_filter_tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("filter_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["filter_id"], ["budget_filters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("filter_id", "tag_id", name="uq_filter_tag"),
    )
    op.create_index("ix_budget_filter_tags_tag_id", "budget_filter_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_budget_filter_tags_tag_id", table_name="budget_filter_tags")
    op.drop_table("budget_filter_tags")
