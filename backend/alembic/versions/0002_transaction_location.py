"""Transaction location capture (opt-in mobile quick-add).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transactions", sa.Column("latitude", sa.Float(precision=53), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("longitude", sa.Float(precision=53), nullable=True)
    )
    # Nearby-payee suggestions scan only located rows
    op.create_index(
        "ix_transactions_budget_location",
        "transactions",
        ["budget_id"],
        postgresql_where=sa.text("latitude IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_budget_location", table_name="transactions")
    op.drop_column("transactions", "longitude")
    op.drop_column("transactions", "latitude")
