"""categories say how their savings count; accounts say whether they are emergency fund

A Savings tag counted money *leaving* a category as saved. That is right for an
envelope that feeds a brokerage and wrong for a fund the household keeps and
spends from, so a Savings category now records which it is:

- `sent_out` — outflows count as saved (what the tag always meant);
- `kept_here` — the envelope's balance is the savings.

`categories.savings_mode` is the explicit choice and NULL means "the tags
decide": `sent_out` for Savings, `kept_here` for Emergency fund
(`category_filters.SAVINGS_ROLE`). NULL on every existing row, so nothing
changes on upgrade, and no tag write path ever has to touch the category row.

`accounts.counts_toward_emergency_fund` marks an off-budget savings account as
part of the emergency fund. False everywhere; nothing is guessed.

The server default on the account column is load-bearing beyond the backfill: a
budget snapshot taken before it existed restores through INSERTs that do not
name it (`services/budget_snapshot.py`). The category column is nullable and
needs none.

Revision ID: 4d5612e7c044
Revises: e3f1a8c5d920
Create Date: 2026-09-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4d5612e7c044"
down_revision: Union[str, Sequence[str], None] = "e3f1a8c5d920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("savings_mode", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        "ck_categories_savings_mode",
        "categories",
        "savings_mode IN ('sent_out', 'kept_here')",
    )
    op.add_column(
        "accounts",
        sa.Column(
            "counts_toward_emergency_fund",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("accounts", "counts_toward_emergency_fund")
    op.drop_constraint("ck_categories_savings_mode", "categories", type_="check")
    op.drop_column("categories", "savings_mode")
