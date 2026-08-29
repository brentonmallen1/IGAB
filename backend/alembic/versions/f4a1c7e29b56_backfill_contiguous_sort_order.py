"""backfill_contiguous_sort_order

Category and group positions were assigned four different ways — the budget
page counted the rows it happened to be showing, the API took whatever it was
sent, the wishlist computed max+1, and the YNAB importer set nothing — so a
budget could hold dozens of live categories sharing `sort_order = 0`, which
Postgres returned in a different order on every read. Renumber every live
category contiguously within its group, and every live group within its
budget, in the `(sort_order, name)` order the listings already fall back to:
the arrangement the user has been seeing becomes the one that is stored.

No schema change. Rows already contiguous are left untouched.

Revision ID: f4a1c7e29b56
Revises: e3c7a9d51f28
Create Date: 2026-08-27 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a1c7e29b56'
down_revision: Union[str, Sequence[str], None] = 'e3c7a9d51f28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE categories c SET sort_order = r.pos"
            " FROM (SELECT id, ROW_NUMBER() OVER ("
            "   PARTITION BY category_group_id ORDER BY sort_order, name, id) - 1 AS pos"
            "   FROM categories WHERE is_deleted = false) r"
            " WHERE c.id = r.id AND c.sort_order <> r.pos"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE category_groups g SET sort_order = r.pos"
            " FROM (SELECT id, ROW_NUMBER() OVER ("
            "   PARTITION BY budget_id ORDER BY sort_order, name, id) - 1 AS pos"
            "   FROM category_groups WHERE is_deleted = false) r"
            " WHERE g.id = r.id AND g.sort_order <> r.pos"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Deliberately a no-op: the old positions were not information (ties
    # rendered in arbitrary order), and the renumbered ones are a valid
    # arrangement under every earlier revision.
    pass
