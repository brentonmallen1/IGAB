"""simplefin sync enhancements: rate limiting, account tracking, transaction linking

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-21 00:00:00.000000

Adds split-quota rate limiting (global vs per-account), per-account sync state,
transaction link tracking for manual/synced match reconciliation, and the
transaction_matches table for pending/accepted/rejected match review.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── simplefin_connections ────────────────────────────────────────────────
    op.add_column("simplefin_connections", sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("simplefin_connections", sa.Column("daily_sync_time", sa.Time(), nullable=True))
    op.add_column("simplefin_connections", sa.Column("global_requests_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("simplefin_connections", sa.Column("account_requests_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("simplefin_connections", sa.Column("last_sync_error", sa.Text(), nullable=True))
    op.add_column("simplefin_connections", sa.Column("last_sync_error_at", sa.DateTime(timezone=True), nullable=True))

    # ── accounts ────────────────────────────────────────────────────────────
    op.add_column("accounts", sa.Column("simplefin_sync_enabled", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("accounts", sa.Column("first_sync_complete", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("accounts", sa.Column("last_simplefin_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounts", sa.Column("simplefin_balance", sa.Numeric(19, 4), nullable=True))

    # ── transactions: link columns ───────────────────────────────────────────
    op.add_column("transactions", sa.Column("linked_transaction_id", sa.UUID(), nullable=True))
    op.add_column("transactions", sa.Column("link_confidence", sa.Numeric(3, 2), nullable=True))
    op.create_foreign_key(
        "fk_transaction_linked",
        "transactions",
        "transactions",
        ["linked_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── transaction_matches ──────────────────────────────────────────────────
    op.create_table(
        "transaction_matches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("synced_transaction_id", sa.UUID(), nullable=False),
        sa.Column("manual_transaction_id", sa.UUID(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["synced_transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transaction_matches_status", "transaction_matches", ["status"])
    op.create_index("ix_transaction_matches_synced", "transaction_matches", ["synced_transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_transaction_matches_synced")
    op.drop_index("ix_transaction_matches_status")
    op.drop_table("transaction_matches")
    op.drop_constraint("fk_transaction_linked", "transactions", type_="foreignkey")
    op.drop_column("transactions", "link_confidence")
    op.drop_column("transactions", "linked_transaction_id")
    op.drop_column("accounts", "simplefin_balance")
    op.drop_column("accounts", "last_simplefin_sync_at")
    op.drop_column("accounts", "first_sync_complete")
    op.drop_column("accounts", "simplefin_sync_enabled")
    op.drop_column("simplefin_connections", "last_sync_error_at")
    op.drop_column("simplefin_connections", "last_sync_error")
    op.drop_column("simplefin_connections", "account_requests_today")
    op.drop_column("simplefin_connections", "global_requests_today")
    op.drop_column("simplefin_connections", "daily_sync_time")
    op.drop_column("simplefin_connections", "sync_enabled")
