"""transactions: remember the category a delete took away

Revision ID: b6d3f81a04e7
Revises: a4c9e17d3b58
Create Date: 2026-08-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6d3f81a04e7"
down_revision: Union[str, Sequence[str], None] = "a4c9e17d3b58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Provenance for a row whose category was deleted out from under it.

    Deleting a category now clears `category_id` so the row is honestly
    uncategorized; these two columns keep what it used to be, for display
    ("was: Groceries") and so undo can find its own rows without carrying a
    list of ids. Schema only — no existing data is touched here. Orphans left
    by earlier deletes are repaired by the hygiene action, which moves real
    money and so must be visible and undoable rather than silent.
    """
    op.add_column(
        "transactions",
        sa.Column("prior_category_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("transactions", sa.Column("prior_category_name", sa.String(255), nullable=True))
    op.create_foreign_key(
        "fk_transactions_prior_category_id_categories",
        "transactions",
        "categories",
        ["prior_category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Undo looks rows up by exactly this column.
    op.create_index(
        "ix_transactions_prior_category_id", "transactions", ["prior_category_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_prior_category_id", table_name="transactions")
    op.drop_constraint(
        "fk_transactions_prior_category_id_categories", "transactions", type_="foreignkey"
    )
    op.drop_column("transactions", "prior_category_name")
    op.drop_column("transactions", "prior_category_id")
