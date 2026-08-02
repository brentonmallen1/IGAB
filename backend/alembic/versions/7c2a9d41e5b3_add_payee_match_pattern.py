"""add_payee_match_pattern

Revision ID: 7c2a9d41e5b3
Revises: 00d4fee0f0a8
Create Date: 2026-08-02 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c2a9d41e5b3'
down_revision: Union[str, Sequence[str], None] = '00d4fee0f0a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'payees',
        sa.Column('match_pattern', sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('payees', 'match_pattern')
