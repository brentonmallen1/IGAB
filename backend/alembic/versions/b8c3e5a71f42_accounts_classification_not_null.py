"""make accounts.classification NOT NULL

Revision ID: b8c3e5a71f42
Revises: a3f7c1d84e26
Create Date: 2026-08-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c3e5a71f42"
down_revision: Union[str, Sequence[str], None] = "a3f7c1d84e26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A NULL classification is a silent hole, not a state.

    Every rule that asks `classification == 'liability'` gets NULL back for
    such a row — and so does its negation, because SQL three-valued logic makes
    `NOT NULL` unknown rather than true. Both the asset arm and the liability
    arm decline, and the row falls through to whatever default sits at the
    bottom. `activity_class.py` had to coalesce the column to 'asset' to keep
    four classification rules alive, and the companion-liability work about to
    land has the identical shape: `ensure_for_account` fires on
    `classification == 'liability'`, so a NULL row is skipped in silence and
    keeps exactly the dead-end state that work exists to close.

    a4d7e2c96b18 already made the hole unreachable — accounts.account_type_id
    is NOT NULL with an FK to account_types, whose own classification is NOT
    NULL, and apply_type is the only writer. The backfill below repeats that
    derivation anyway rather than trusting the reasoning: an install whose data
    disagrees gets repaired instead of a failed migration.
    """
    op.execute(
        """
        UPDATE accounts a
        SET classification = at.classification
        FROM account_types at
        WHERE at.id = a.account_type_id AND a.classification IS NULL
        """
    )
    op.alter_column("accounts", "classification", existing_type=sa.String(20), nullable=False)


def downgrade() -> None:
    op.alter_column("accounts", "classification", existing_type=sa.String(20), nullable=True)
