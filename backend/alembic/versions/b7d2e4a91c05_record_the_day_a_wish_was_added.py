"""record the day a wish was added

A cooling-off can be set in days after a wish was added, and "added" is the
person's date, not the server's: `created_at` is an instant, and its date is
already tomorrow every evening west of UTC. Existing rows are backfilled with
the date every reader took from that instant until now, so nothing on the
list moves.

Revision ID: b7d2e4a91c05
Revises: 1edb396867cb
Create Date: 2026-09-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7d2e4a91c05'
down_revision: Union[str, Sequence[str], None] = '1edb396867cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wishlist_items", sa.Column("added_on", sa.Date(), nullable=True))
    op.execute("UPDATE wishlist_items SET added_on = (created_at AT TIME ZONE 'UTC')::date")


def downgrade() -> None:
    op.drop_column("wishlist_items", "added_on")
