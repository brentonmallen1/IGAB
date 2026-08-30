"""archive_rename

`is_hidden` never meant "not on screen". A hidden category could not be
assigned to (`IS_ASSIGNABLE`), could not be filed to (`IS_CATEGORIZABLE`), and
was off the grid by default — while still holding money and still moving Ready
to Assign. That is an archive, and calling it hidden is what made the state
impossible to describe: the flow it needed, the reports position it needed, and
the money it silently stranded all went unbuilt because nobody could say what
the flag meant.

Rename it on `categories` and `category_groups`. `budget_view_placements.is_hidden`
is deliberately untouched — that one really is per-view visibility, and is the
only correct use of the word in the schema.

`archived_at` is new and nullable. The archived listing needs "date archived"
and `updated_at` cannot serve, since any edit bumps it. Existing rows get NULL
rather than an invented timestamp, and the UI renders that as unknown.

The Credit Card Payments group is un-archived on the way through. It was only
ever flagged to keep card envelopes out of the pickers, which `IS_ASSIGNABLE`
now does by naming `LINKED_TO_CARD` outright — so leaving the flag set would
list a live, in-daily-use group among the user's archived envelopes.

Revision ID: a1f9c3d47b28
Revises: c4d8b91e7a63
Create Date: 2026-08-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1f9c3d47b28"
down_revision: str | None = "c4d8b91e7a63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("categories", "category_groups"):
        op.alter_column(table, "is_hidden", new_column_name="is_archived")
        op.add_column(table, sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

    # A group whose every live category is a card envelope is structural, not
    # archived. Matched on shape rather than on the name, so a renamed group
    # is still repaired and a user's own group called "Credit Card Payments"
    # is not.
    op.execute(
        """
        UPDATE category_groups g
           SET is_archived = false
         WHERE g.is_archived
           AND EXISTS (
                 SELECT 1 FROM categories c
                  WHERE c.category_group_id = g.id AND NOT c.is_deleted
               )
           AND NOT EXISTS (
                 SELECT 1 FROM categories c
                  WHERE c.category_group_id = g.id AND NOT c.is_deleted
                    AND c.linked_account_id IS NULL
               )
        """
    )


def downgrade() -> None:
    # The Credit Card Payments repair is not undone: re-hiding those groups
    # would restore a state the new IS_ASSIGNABLE no longer depends on, and
    # would hide them from the pre-rename grid for no reason.
    for table in ("categories", "category_groups"):
        op.drop_column(table, "archived_at")
        op.alter_column(table, "is_archived", new_column_name="is_hidden")
