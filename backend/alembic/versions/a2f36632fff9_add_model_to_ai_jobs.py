"""add_model_to_ai_jobs

Revision ID: a2f36632fff9
Revises: a1f4c9d27e6b
Create Date: 2026-08-16 05:06:04.379176

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2f36632fff9'
down_revision: Union[str, Sequence[str], None] = 'a1f4c9d27e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('ai_jobs', sa.Column('model', sa.String(100), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ai_jobs', 'model')
