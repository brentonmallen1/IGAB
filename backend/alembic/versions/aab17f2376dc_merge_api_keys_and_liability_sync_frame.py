"""merge api keys and liability sync frame

Two branches were written off the same parent and merged the same day, so the
chain forked and `alembic upgrade head` had no single head to name. It is the
API image's CMD, so the container would have exited rather than started. This
revision joins the two tips back into one and changes no schema: the branches
touch different tables and neither depends on the other.

Revision ID: aab17f2376dc
Revises: c4e8b1d70a35, d5a91c3e04b7
Create Date: 2026-09-18 19:38:12.414292

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aab17f2376dc'
down_revision: Union[str, Sequence[str], None] = ('c4e8b1d70a35', 'd5a91c3e04b7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
