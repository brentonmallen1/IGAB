"""attachment soft delete

Revision ID: a3c8e5b17f42
Revises: f9a2d6c47e13
Create Date: 2026-09-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3c8e5b17f42"
down_revision: Union[str, Sequence[str], None] = "f9a2d6c47e13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Soft delete for attachments, so undo can restore a deleted receipt.

    Deleting used to unlink the bytes immediately — irreversible by
    construction. Now the row flips is_deleted (stamping deleted_at) and
    the files stay on disk until attachment_sweep purges rows past the
    grace period; within it, ⌘Z brings the receipt back whole.
    """
    op.add_column(
        "transaction_attachments",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "transaction_attachments",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transaction_attachments", "deleted_at")
    op.drop_column("transaction_attachments", "is_deleted")
