"""transactions: remember the amount the bank overwrote

Revision ID: c3e7a92d5f18
Revises: b6d3f81a04e7
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3e7a92d5f18"
down_revision: Union[str, Sequence[str], None] = "b6d3f81a04e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Provenance for a row whose amount the bank changed at posting.

    `entered_date` already remembers a date the bank overwrote; this is its
    twin for the amount. A pending auth hold posting as a larger charge, or
    an accepted review of a changed amount, writes the bank's figure to
    `amount` and keeps the prior one here once — so the bank-record tooltip
    can say "amount updated from X" instead of the row silently changing.
    Schema only.
    """
    op.add_column(
        "transactions", sa.Column("entered_amount", sa.Numeric(19, 4), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("transactions", "entered_amount")
