"""add_fk_indexes

Postgres does not index foreign-key columns automatically, and the schema
left nearly all of them unindexed. Every referential-integrity check then
sequential-scans the referencing table — deleting a budget cascades over
transactions whose three self-referential FKs (parent/transfer/linked) each
trigger a full scan per deleted row, making large-budget deletes roughly
O(N²). The same missing indexes cost every register and report query that
filters by budget/account/category/payee.

Single-column FK indexes are skipped where an existing PK, unique, or index
already leads with that column (e.g. uq_account_budget_name covers
accounts.budget_id). transactions.account_id gets a composite (account_id,
date) so the register's per-account date-ordered scans are covered by the
same index that serves RI checks.

Revision ID: f2a8c5d17b39
Revises: e9b3f6a25c17
Create Date: 2026-08-19 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a8c5d17b39"
down_revision: Union[str, Sequence[str], None] = "e9b3f6a25c17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (index name, table, columns) — mirrored by index=True / Index() in db/models.py
INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_transactions_budget_id", "transactions", ["budget_id"]),
    ("ix_transactions_account_date", "transactions", ["account_id", "date"]),
    ("ix_transactions_payee_id", "transactions", ["payee_id"]),
    ("ix_transactions_category_id", "transactions", ["category_id"]),
    ("ix_transactions_transfer_id", "transactions", ["transfer_id"]),
    ("ix_transactions_parent_transaction_id", "transactions", ["parent_transaction_id"]),
    ("ix_transactions_linked_transaction_id", "transactions", ["linked_transaction_id"]),
    ("ix_payees_default_category_id", "payees", ["default_category_id"]),
    ("ix_payees_transfer_account_id", "payees", ["transfer_account_id"]),
    ("ix_categories_budget_id", "categories", ["budget_id"]),
    ("ix_categories_linked_account_id", "categories", ["linked_account_id"]),
    ("ix_categories_linked_liability_id", "categories", ["linked_liability_id"]),
    ("ix_budget_assignments_budget_id", "budget_assignments", ["budget_id"]),
    ("ix_budget_moves_budget_id", "budget_moves", ["budget_id"]),
    ("ix_budget_moves_from_category_id", "budget_moves", ["from_category_id"]),
    ("ix_budget_moves_to_category_id", "budget_moves", ["to_category_id"]),
    ("ix_change_log_user_id", "change_log", ["user_id"]),
    ("ix_scheduled_transactions_budget_id", "scheduled_transactions", ["budget_id"]),
    ("ix_scheduled_transactions_account_id", "scheduled_transactions", ["account_id"]),
    ("ix_scheduled_transactions_payee_id", "scheduled_transactions", ["payee_id"]),
    ("ix_scheduled_transactions_category_id", "scheduled_transactions", ["category_id"]),
    (
        "ix_scheduled_transactions_transfer_account_id",
        "scheduled_transactions",
        ["transfer_account_id"],
    ),
    ("ix_reconciliation_snapshots_account_id", "reconciliation_snapshots", ["account_id"]),
    (
        "ix_reconciliation_snapshots_adjustment_transaction_id",
        "reconciliation_snapshots",
        ["adjustment_transaction_id"],
    ),
    ("ix_budget_view_categories_category_id", "budget_view_categories", ["category_id"]),
    ("ix_simplefin_connections_user_id", "simplefin_connections", ["user_id"]),
    ("ix_import_batches_budget_id", "import_batches", ["budget_id"]),
    ("ix_transaction_matches_synced_transaction_id", "transaction_matches", ["synced_transaction_id"]),
    ("ix_transaction_matches_manual_transaction_id", "transaction_matches", ["manual_transaction_id"]),
    ("ix_transaction_attachments_transaction_id", "transaction_attachments", ["transaction_id"]),
    ("ix_ai_jobs_transaction_id", "ai_jobs", ["transaction_id"]),
    ("ix_ai_jobs_attachment_id", "ai_jobs", ["attachment_id"]),
    ("ix_category_tags_tag_id", "category_tags", ["tag_id"]),
    ("ix_payee_tags_tag_id", "payee_tags", ["tag_id"]),
]


def upgrade() -> None:
    """Upgrade schema."""
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    """Downgrade schema."""
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
