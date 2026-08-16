"""add_subtitle_to_categories

Revision ID: c7d94a1b3e58
Revises: a2f36632fff9
Create Date: 2026-08-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d94a1b3e58'
down_revision: Union[str, Sequence[str], None] = 'a2f36632fff9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('categories', sa.Column('subtitle', sa.String(100), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('categories', 'subtitle')
