"""sync run balance drift

Revision ID: a9c4e17d52b0
Revises: 7c1e5b9d3a42
Create Date: 2026-09-17 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a9c4e17d52b0'
down_revision: Union[str, Sequence[str], None] = '7c1e5b9d3a42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sync_runs',
        sa.Column(
            'balance_drift',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column('sync_runs', 'balance_drift', server_default=None)
    op.add_column(
        'sync_run_accounts', sa.Column('bank_balance', sa.Numeric(precision=19, scale=4), nullable=True)
    )
    op.add_column(
        'sync_run_accounts',
        sa.Column('ledger_cleared_balance', sa.Numeric(precision=19, scale=4), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sync_run_accounts', 'ledger_cleared_balance')
    op.drop_column('sync_run_accounts', 'bank_balance')
    op.drop_column('sync_runs', 'balance_drift')
