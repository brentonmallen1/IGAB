"""Projected interest rows: mark a loan's modelled monthly interest charge.

A loan payment posts as a transfer of the whole amount into the loan
account; the lender's interest is a separate, payee-less outflow on the loan
that nothing in the app writes, so the register and the loan's balance ran
one month of interest low. The app now writes that row itself from the
terms on file (`services/projected_interest.py`), and this column is how it
knows which rows are its own.

`projected_interest_month` is the month the row stands for (its first day).
NULL on every other row — and on a projection the person has adopted by
editing it, or one the app has retired. A DELETED row that still carries the
month is a tombstone: the person declined that month, and it is never
projected again.

The partial unique index allows one LIVE projection per account and month;
tombstones sit outside it, so declining a month and the app's own retire
never collide with each other.

No data migration: nothing written before this is a projection. Downgrade
drops the marking only; any projection then standing stays in the register
as an ordinary uncleared interest row, which is what it already counted as.

Revision ID: f4a7c2d91b3e
Revises: e53562b192c5
"""

import sqlalchemy as sa
from alembic import op

revision = "f4a7c2d91b3e"
down_revision = "e53562b192c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("projected_interest_month", sa.Date(), nullable=True),
    )
    op.create_index(
        "uq_transactions_account_projected_interest_month",
        "transactions",
        ["account_id", "projected_interest_month"],
        unique=True,
        postgresql_where=sa.text("projected_interest_month IS NOT NULL AND NOT is_deleted"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_transactions_account_projected_interest_month",
        table_name="transactions",
    )
    op.drop_column("transactions", "projected_interest_month")
