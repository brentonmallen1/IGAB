"""add bank amount and payee provenance

Revision ID: cdea6bae6ab3
Revises: c9e4f7a31d25
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "cdea6bae6ab3"
down_revision: Union[str, Sequence[str], None] = "c9e4f7a31d25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The bank's own amount and payee string, kept verbatim alongside the
    # user's ledger values. Nullable: rows synced before this migration have
    # no record of what the bank reported.
    op.add_column(
        "transactions", sa.Column("bank_amount", sa.Numeric(precision=19, scale=4), nullable=True)
    )
    op.add_column("transactions", sa.Column("bank_payee", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "bank_payee")
    op.drop_column("transactions", "bank_amount")
