"""account_budget_start_date: the day an account joined the budget

A synced account arrives with whatever history the bank kept. A credit card
brought in on the 29th came with three months of it, every swipe auto-filed
into an envelope funded for one month — so the budget filled with red for
money spent before it knew the card existed. That debt is opening position.
It belongs in the card's Uncovered, retired by assigning to the card, not
covered from Ready to Assign.

`budget_start_date` is where the answer lives. Rows dated before it are not
auto-categorized on first sync, and an uncategorized one is not flagged as
needing a category.

NULL means "behave exactly as before", and every existing account starts
NULL, so this migration moves no figure anywhere. `accounts.created_at` is
the right default to *offer* when asking and the wrong rule to obey on its
own: it resets when an account is deleted and re-added, it cannot be
corrected afterwards, and it is a UTC timestamp where transaction dates are
local — a midnight boundary between them nobody would ever see coming.

Revision ID: d9f2a4c61e08
Revises: c8e1f3b47d92
Create Date: 2026-08-29 16:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9f2a4c61e08"
down_revision: str | Sequence[str] | None = "c8e1f3b47d92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("accounts", sa.Column("budget_start_date", sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("accounts", "budget_start_date")
