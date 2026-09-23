"""card bill due date as a cycle, not only a day of the month

A card billed on a fixed-length cycle — 28 days, 31 days — walks its due date
through the calendar, so "the 17th" read off one statement is the 14th by
July. Three columns hold the rule instead of that one observation:

- liabilities.payment_due_kind — 'day_of_month' (what every existing row is,
  and stays) or 'cycle_days'.
- liabilities.payment_due_cycle_days — the cycle's length.
- liabilities.payment_due_anchor — the last due date the user actually saw.

Nothing back-fills: an existing `payment_due_day` keeps meaning exactly what
it meant, under the kind it already implied.

Revision ID: e7b3c0d48a19
Revises: aab17f2376dc
Create Date: 2026-09-22 09:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b3c0d48a19"
down_revision: Union[str, Sequence[str], None] = "aab17f2376dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOT NULL with a server default: every existing row already states its
    # due date as a day of the month, so that is what they are, and a nullable
    # kind would mean the read path had to guess at the one thing this column
    # exists to stop it guessing at.
    op.add_column(
        "liabilities",
        sa.Column(
            "payment_due_kind",
            sa.String(length=20),
            nullable=False,
            server_default="day_of_month",
        ),
    )
    op.add_column("liabilities", sa.Column("payment_due_cycle_days", sa.Integer(), nullable=True))
    op.add_column("liabilities", sa.Column("payment_due_anchor", sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("liabilities", "payment_due_anchor")
    op.drop_column("liabilities", "payment_due_cycle_days")
    op.drop_column("liabilities", "payment_due_kind")
