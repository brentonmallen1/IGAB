"""Record when a wish was dropped, not just when it was bought

`done_at` had no mirror, so the only trace of a dropped wish was `updated_at`
— last-touch, which any later edit moves. That makes the statistic worth
having unstateable: "you talked yourself out of N purchases worth $X during
the cooling-off period" is the one figure that reinforces the habit the
wishlist exists for, and it needs a real drop date.

Backfilled from `updated_at` for wishes already dropped. That is an
approximation and the only one available: for a wish dropped and never touched
again it is exact, and for one edited afterwards it is late. New drops are
stamped properly.

Revision ID: e7c3a91d4b28
Revises: c5a7e2d91f38
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7c3a91d4b28"
down_revision: str | None = "d4b6f2a81e57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("wishlist_items", sa.Column("dropped_at", sa.Date(), nullable=True))
    op.execute(
        """
        UPDATE wishlist_items
           SET dropped_at = updated_at::date
         WHERE status = 'dropped' AND dropped_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("wishlist_items", "dropped_at")
