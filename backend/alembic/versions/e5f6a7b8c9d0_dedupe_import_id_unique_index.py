"""deduplicate import_id and add unique partial index

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-22 00:00:00.000000

Cleans up duplicate (account_id, import_id) rows caused by missing constraint,
keeping the most-recently-created copy and soft-deleting extras.
Then adds a unique partial index to prevent recurrence.
"""

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "9d26da8b9ed4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Soft-delete duplicate import_id rows, keeping the newest per (account_id, import_id).
    op.execute("""
        UPDATE transactions
        SET is_deleted = true
        WHERE id IN (
            SELECT id FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY account_id, import_id
                        ORDER BY created_at DESC
                    ) AS rn
                FROM transactions
                WHERE import_id IS NOT NULL
                  AND is_deleted = false
            ) ranked
            WHERE rn > 1
        )
    """)

    op.execute("""
        CREATE UNIQUE INDEX ix_transactions_account_import_id
        ON transactions (account_id, import_id)
        WHERE import_id IS NOT NULL AND is_deleted = false
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_transactions_account_import_id")
