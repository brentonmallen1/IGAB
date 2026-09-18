"""sync run change batch

Revision ID: b7f2a91c3d54
Revises: a9c4e17d52b0
Create Date: 2026-09-18 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7f2a91c3d54'
down_revision: Union[str, Sequence[str], None] = 'a9c4e17d52b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sync_runs', sa.Column('change_batch_id', sa.UUID(), nullable=True))
    op.add_column('sync_runs', sa.Column('undone_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sync_runs', 'undone_at')
    op.drop_column('sync_runs', 'change_batch_id')
