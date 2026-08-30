"""accounts, payees, groups, categories, tags: unique names among live rows only

Revision ID: c4d8b91e7a63
Revises: b7e4f13a92c5
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d8b91e7a63"
down_revision: str | Sequence[str] | None = "b7e4f13a92c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: (table, columns, old constraint, live index, name column length).
#: The length is what the downgrade's collision rename has to fit inside.
_TABLES = (
    ("accounts", ["budget_id", "name"], "uq_account_budget_name", "uq_account_budget_name_live", 100),
    ("payees", ["budget_id", "name"], "uq_payee_budget_name", "uq_payee_budget_name_live", 255),
    (
        "category_groups",
        ["budget_id", "name"],
        "uq_category_group_budget_name",
        "uq_category_group_budget_name_live",
        100,
    ),
    (
        "categories",
        ["category_group_id", "name"],
        "uq_category_group_name",
        "uq_category_group_name_live",
        100,
    ),
    ("tags", ["budget_id", "name"], "uq_tag_budget_name", "uq_tag_budget_name_live", 50),
)


def upgrade() -> None:
    """Deletes are soft, but these unique constraints were not.

    a4c9e17d3b58 fixed exactly this for budget_views and budget_filters and
    left the other five tables carrying the defect. Deleting an account — or
    undoing its creation, which soft-deletes it the same way — hid it from
    every list while its name stayed burned in the full constraint, so
    recreating it returned "An account with that name already exists in this
    budget" against a list showing no such account.

    Scope uniqueness to live rows: a deleted name is reusable, and
    soft-deleted rows may share names freely. Live rows were already unique
    under the stricter constraint, so no existing row can violate the new
    index.
    """
    for table, cols, old, live, _ in _TABLES:
        op.drop_constraint(old, table, type_="unique")
        op.create_index(
            live,
            table,
            cols,
            unique=True,
            postgresql_where=sa.text("NOT is_deleted"),
        )


def downgrade() -> None:
    # A full constraint cannot hold if soft-deleted rows share a live name;
    # rename the deleted collisions out of the way before restoring it.
    for table, cols, old, live, length in _TABLES:
        key = ", ".join(cols)
        op.execute(
            f"""
            UPDATE {table} SET name = left(name, {length - 9}) || '~' || left(id::text, 8)
            WHERE is_deleted AND ({key}) IN (
                SELECT {key} FROM {table} GROUP BY {key} HAVING count(*) > 1
            )
            """
        )
        op.drop_index(live, table_name=table)
        op.create_unique_constraint(old, table, cols)
