"""record the day a wish was affirmed

The review cadence counts days from "still want it" to today, and both ends
have to be the same kind of day. `last_affirmed_at` is an instant, so its
date is already tomorrow every evening west of UTC, while `added_on` is
deliberately the person's own date — the two were being compared to each
other. Same shape and same reason as `added_on` (b7d2e4a91c05).

Existing rows are backfilled with the date every reader took from that
instant until now, so nothing on the list moves.

Revision ID: c4a1f7e28b63
Revises: e7b3c0d48a19
Create Date: 2026-09-22 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4a1f7e28b63'
down_revision: Union[str, Sequence[str], None] = 'e7b3c0d48a19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wishlist_items", sa.Column("affirmed_on", sa.Date(), nullable=True))
    op.execute(
        "UPDATE wishlist_items SET affirmed_on = (last_affirmed_at AT TIME ZONE 'UTC')::date "
        "WHERE last_affirmed_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("wishlist_items", "affirmed_on")
