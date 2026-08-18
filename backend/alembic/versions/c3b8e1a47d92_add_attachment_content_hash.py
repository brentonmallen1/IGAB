"""add content_hash to transaction_attachments

Detects the same receipt being submitted twice. On a budgeting app a duplicate
receipt is a double-counted expense, not just clutter.

Nullable with no backfill: the hash is of the bytes as *uploaded*, and existing
rows store a re-encoded WebP whose hash would never match a resubmission of the
original file. A wrong hash is worse than none — it would silently reject a
legitimate upload — so historical rows simply never match.

Revision ID: c3b8e1a47d92
Revises: f4a7d2c91b56
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3b8e1a47d92"
down_revision: str | Sequence[str] | None = "f4a7d2c91b56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transaction_attachments",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_transaction_attachments_content_hash",
        "transaction_attachments",
        ["content_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transaction_attachments_content_hash",
        table_name="transaction_attachments",
    )
    op.drop_column("transaction_attachments", "content_hash")
