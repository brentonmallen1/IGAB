"""add_format_settings

Revision ID: 00d4fee0f0a8
Revises: 0001
Create Date: 2026-07-27 00:32:16.921835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00d4fee0f0a8'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'budgets',
        sa.Column('number_format', sa.String(length=20), nullable=False, server_default='comma_dot')
    )
    op.add_column(
        'budgets',
        sa.Column('date_format', sa.String(length=10), nullable=False, server_default='mdy')
    )
    op.add_column(
        'budgets',
        sa.Column('time_format', sa.String(length=5), nullable=False, server_default='12h')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('budgets', 'time_format')
    op.drop_column('budgets', 'date_format')
    op.drop_column('budgets', 'number_format')
