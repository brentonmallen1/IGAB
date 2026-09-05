"""wishlist pinned priorities

Revision ID: d4b7f2a91c36
Revises: c41d8b6ae973
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4b7f2a91c36"
down_revision: Union[str, Sequence[str], None] = "c41d8b6ae973"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A wish pinned as a top priority — an explicit, capped choice.

    Default false for every existing wish: the strip used to auto-promote the
    top three of the queue, which showed items nobody chose; from here it
    shows only what someone pinned, so everyone starts unpinned.
    """
    op.add_column(
        "wishlist_items",
        sa.Column("is_priority", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("wishlist_items", "is_priority")
