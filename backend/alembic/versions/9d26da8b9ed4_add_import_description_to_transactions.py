"""add_import_description_to_transactions

Revision ID: 9d26da8b9ed4
Revises: 91a816557290
Create Date: 2026-04-21 22:24:51.800301

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d26da8b9ed4'
down_revision: Union[str, Sequence[str], None] = '91a816557290'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('import_description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('transactions', 'import_description')
