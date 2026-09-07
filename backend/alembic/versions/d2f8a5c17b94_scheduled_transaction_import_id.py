"""scheduled transaction import id

A future-dated row in a YNAB register export is the next instance of a
scheduled transaction (YNAB exports no cadence, only the dated instance). The
importer now holds such rows out of the register and creates a one-off
schedule for each. That gives the importer a second table it must not fill
twice: importing the same file again has to find the schedules it made last
time, the way `transactions.import_id` already lets it find the rows.

The partial unique index mirrors `uq_transactions_account_import_id`, keyed by
budget rather than account because the identity already carries the account.

Revision ID: d2f8a5c17b94
Revises: c4e7b2a91d63
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2f8a5c17b94"
down_revision: str | Sequence[str] | None = "c4e7b2a91d63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scheduled_transactions", sa.Column("import_id", sa.String(255), nullable=True)
    )
    op.create_index(
        "uq_scheduled_transactions_budget_import_id",
        "scheduled_transactions",
        ["budget_id", "import_id"],
        unique=True,
        postgresql_where=sa.text("import_id IS NOT NULL AND NOT is_deleted"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_scheduled_transactions_budget_import_id", table_name="scheduled_transactions"
    )
    op.drop_column("scheduled_transactions", "import_id")
