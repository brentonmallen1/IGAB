"""add_transaction_bank_posted_date

Revision ID: a1f4c9d27e6b
Revises: e5a2c7f91b04
Create Date: 2026-08-15 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f4c9d27e6b'
down_revision: Union[str, Sequence[str], None] = 'e5a2c7f91b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'transactions',
        sa.Column('bank_posted_date', sa.Date(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('transactions', 'bank_posted_date')
