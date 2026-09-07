"""archive leftover "Hidden Categories" groups

A YNAB import used to create the export's "Hidden Categories" group as an
ordinary group; the importer now archives it on arrival (its history imports,
the rows just do not clutter the grid), but a budget imported before that
change still shows the group — and once its categories are archived by hand,
it is a header over nothing that the delete flow then asks to move history
out of.

This archives any live, unarchived group of that name whose every live
category is already archived. Nothing else: a group of that name still
holding an active envelope is left for the person to decide.

Revision ID: a7d3b9e15c62
Revises: f1c4e8a92b57
Create Date: 2026-09-06

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a7d3b9e15c62"
down_revision: str | Sequence[str] | None = "f1c4e8a92b57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE category_groups g
        SET is_archived = TRUE, archived_at = now()
        WHERE lower(g.name) = 'hidden categories'
          AND NOT g.is_deleted
          AND NOT g.is_archived
          AND NOT EXISTS (
              SELECT 1 FROM categories c
              WHERE c.category_group_id = g.id
                AND NOT c.is_deleted
                AND NOT c.is_archived
          )
        """
    )


def downgrade() -> None:
    # Lossy on purpose: the groups this archived cannot be told apart from
    # ones archived by hand afterwards.
    pass
