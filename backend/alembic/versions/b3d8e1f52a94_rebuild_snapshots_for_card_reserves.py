"""Rebuild category snapshots after the card reserve model changed

Revision ID: b3d8e1f52a94
Revises: a1f9c3d47b28
Create Date: 2026-08-30

Data only — no schema change, and none is needed: snapshot rows hold the
*unadjusted* `monthly_end_balances(assigned, activity)` series, and any
category a card touched is overridden at read time out of `card_funding`.
Nothing persisted encodes the old model.

It ships anyway. `igab.db.invalidation` treats meta-row presence as the sole
validity signal, so a code-only deploy leaves every existing snapshot marked
valid. That happens to be harmless today, and relying on it is exactly the
coupling that rots — one forced rebuild is one DELETE on a table with one row
per budget, and it puts the change where a bisect can find it.

What changed for a reader arriving here from a support question: assignments
to a card's payment category now retire debt riding on that card before they
reserve ("Two Ledgers, One Debt"). Historical figures move for any budget that
ever assigned to a card while something rode on it — refunds after such an
assignment now credit the envelope instead of vanishing, Ready to Assign rises
by boundary write-offs a stale ride caused, and over-reserves the check used to
excuse start being named. No user data is rewritten: assignments and
transactions are untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3d8e1f52a94"
down_revision: str | Sequence[str] | None = "a1f9c3d47b28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Dropping the meta rows is what marks the cache invalid; the snapshot
    # rows themselves are rebuilt from source on the next summary read.
    op.execute(sa.text("DELETE FROM budget_snapshot_meta"))


def downgrade() -> None:
    # Symmetric: going back also changes what a reserve means, so the cache
    # has to be rebuilt in that direction too.
    op.execute(sa.text("DELETE FROM budget_snapshot_meta"))
