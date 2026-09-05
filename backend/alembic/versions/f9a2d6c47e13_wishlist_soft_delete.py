"""wishlist soft delete

Revision ID: f9a2d6c47e13
Revises: e7c3a5f18d92
Create Date: 2026-09-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f9a2d6c47e13"
down_revision: Union[str, Sequence[str], None] = "e7c3a5f18d92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Soft delete for wishes and projects, so undo can restore them.

    The undo machinery flips is_deleted rather than re-inserting rows — a
    hard-deleted wish was beyond its reach, and ⌘Z after deleting one
    silently reverted an older, unrelated change instead.
    """
    op.add_column(
        "wishlist_items",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "wishlist_projects",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("wishlist_projects", "is_deleted")
    op.drop_column("wishlist_items", "is_deleted")
