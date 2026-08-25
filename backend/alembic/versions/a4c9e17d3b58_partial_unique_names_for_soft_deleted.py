"""views and filters: unique names among live rows only

Revision ID: a4c9e17d3b58
Revises: f7b2a4c98e13
Create Date: 2026-08-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4c9e17d3b58"
down_revision: Union[str, Sequence[str], None] = "f7b2a4c98e13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Deletes are soft, but the unique constraints were not.

    Deleting a view (or filter) hid it from every list while its name stayed
    burned in the full constraint — recreating it returned "already exists"
    against a list showing nothing. Scope uniqueness to live rows so a deleted
    name is reusable; soft-deleted rows may share names freely.
    """
    op.drop_constraint("uq_budget_view_budget_name", "budget_views", type_="unique")
    op.create_index(
        "uq_budget_view_budget_name_live",
        "budget_views",
        ["budget_id", "name"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
    )

    op.drop_constraint("uq_budget_filter_budget_name", "budget_filters", type_="unique")
    op.create_index(
        "uq_budget_filter_budget_name_live",
        "budget_filters",
        ["budget_id", "name"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
    )


def downgrade() -> None:
    # A full constraint cannot hold if soft-deleted rows share a live name;
    # rename the deleted collisions out of the way before restoring it.
    for table in ("budget_views", "budget_filters"):
        op.execute(
            f"""
            UPDATE {table} SET name = left(name, 91) || '~' || left(id::text, 8)
            WHERE is_deleted AND (budget_id, name) IN (
                SELECT budget_id, name FROM {table} GROUP BY budget_id, name HAVING count(*) > 1
            )
            """
        )
    op.drop_index("uq_budget_view_budget_name_live", table_name="budget_views")
    op.create_unique_constraint(
        "uq_budget_view_budget_name", "budget_views", ["budget_id", "name"]
    )
    op.drop_index("uq_budget_filter_budget_name_live", table_name="budget_filters")
    op.create_unique_constraint(
        "uq_budget_filter_budget_name", "budget_filters", ["budget_id", "name"]
    )
