"""rename budget views to filters

Revision ID: c4f8a2e91d07
Revises: b7e21c4f8a03
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c4f8a2e91d07"
down_revision: Union[str, Sequence[str], None] = "b7e21c4f8a03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_constraint(table: str, old: str, new: str) -> None:
    """Rename a constraint only if it is actually there.

    Postgres auto-names primary and foreign keys (no naming_convention is set on
    the metadata), so these names come from whatever CREATE TABLE ran first. That
    is predictable but not guaranteed across every deployment, and a rename that
    is merely cosmetic must not be the thing that fails an upgrade.
    """
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = '{old}' AND conrelid = '{table}'::regclass
            ) THEN
                ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new};
            END IF;
        END $$;
        """
    )


def _rename_index(old: str, new: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_class WHERE relname = '{old}' AND relkind = 'i') THEN
                ALTER INDEX {old} RENAME TO {new};
            END IF;
        END $$;
        """
    )


#: (table after rename, name before, name after)
_CONSTRAINTS = [
    ("budget_filters", "uq_budget_view_budget_name", "uq_budget_filter_budget_name"),
    ("budget_filters", "budget_views_pkey", "budget_filters_pkey"),
    ("budget_filters", "budget_views_budget_id_fkey", "budget_filters_budget_id_fkey"),
    ("budget_filter_categories", "uq_view_category", "uq_filter_category"),
    ("budget_filter_categories", "budget_view_categories_pkey", "budget_filter_categories_pkey"),
    (
        "budget_filter_categories",
        "budget_view_categories_view_id_fkey",
        "budget_filter_categories_filter_id_fkey",
    ),
    (
        "budget_filter_categories",
        "budget_view_categories_category_id_fkey",
        "budget_filter_categories_category_id_fkey",
    ),
]

_INDEXES = [
    ("ix_budget_view_categories_category_id", "ix_budget_filter_categories_category_id"),
]


def upgrade() -> None:
    """Rename only — no column added, dropped or retyped.

    What this table stores is an include-list of category ids: a filter. The
    name "view" is being freed for the thing that regroups categories rather
    than merely narrowing them, which is a different feature.

    Constraints and indexes move with the tables. Postgres keeps their old names
    through a table rename, so without this a constraint called
    uq_budget_view_budget_name would sit on a table called budget_filters —
    exactly the drift this rename exists to remove.
    """
    op.rename_table("budget_views", "budget_filters")
    op.rename_table("budget_view_categories", "budget_filter_categories")
    op.alter_column("budget_filter_categories", "view_id", new_column_name="filter_id")

    for table, old, new in _CONSTRAINTS:
        _rename_constraint(table, old, new)
    for old, new in _INDEXES:
        _rename_index(old, new)


def downgrade() -> None:
    for old, new in _INDEXES:
        _rename_index(new, old)
    for table, old, new in _CONSTRAINTS:
        _rename_constraint(table, new, old)

    op.alter_column("budget_filter_categories", "filter_id", new_column_name="view_id")
    op.rename_table("budget_filter_categories", "budget_view_categories")
    op.rename_table("budget_filters", "budget_views")
