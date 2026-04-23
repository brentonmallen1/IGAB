"""payee mapping_samples and transaction has_sync_source

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-22 00:00:00.000000

Adds:
- payees.mapping_samples (nullable Text) for fuzzy payee resolution
- transactions.has_sync_source (boolean, default False) to flag manual
  transactions that absorbed a synced duplicate via match acceptance
"""

import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payees", sa.Column("mapping_samples", sa.Text(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column(
            "has_sync_source", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    # Backfill: manual transactions that are bidirectionally linked to a synced one
    op.execute("""
        UPDATE transactions
        SET has_sync_source = true
        WHERE linked_transaction_id IS NOT NULL
          AND import_id IS NULL
          AND is_deleted = false
    """)


def downgrade() -> None:
    op.drop_column("transactions", "has_sync_source")
    op.drop_column("payees", "mapping_samples")
