"""add_ai_jobs_and_provenance

Revision ID: b3f1c8a7d2e9
Revises: 7c2a9d41e5b3
Create Date: 2026-08-02 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3f1c8a7d2e9'
down_revision: Union[str, Sequence[str], None] = '7c2a9d41e5b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ai_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'budget_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('budgets.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='queued'),
        sa.Column(
            'payload', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column(
            'available_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'transaction_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('transactions.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'attachment_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('transaction_attachments.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index('ix_ai_jobs_budget_status', 'ai_jobs', ['budget_id', 'status'])
    op.create_index(
        'ix_ai_jobs_queue',
        'ai_jobs',
        ['available_at'],
        postgresql_where=sa.text("status = 'queued'"),
    )

    op.add_column(
        'transactions',
        sa.Column('created_via', sa.String(length=20), nullable=True),
    )

    op.add_column(
        'transaction_attachments',
        sa.Column('storage_path', sa.String(length=500), nullable=True),
    )
    # Backfill storage_path from the current transaction date — matches the
    # on-disk layout for every attachment whose transaction date has not been
    # edited since upload (the layout was YYYY/MM/DD/{txn_id}/{filename}).
    op.execute(
        """
        UPDATE transaction_attachments a
        SET storage_path =
            to_char(t.date, 'YYYY') || '/' ||
            to_char(t.date, 'MM') || '/' ||
            to_char(t.date, 'DD') || '/' ||
            t.id::text || '/' || a.filename
        FROM transactions t
        WHERE t.id = a.transaction_id AND a.storage_path IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('transaction_attachments', 'storage_path')
    op.drop_column('transactions', 'created_via')
    op.drop_index('ix_ai_jobs_queue', table_name='ai_jobs')
    op.drop_index('ix_ai_jobs_budget_status', table_name='ai_jobs')
    op.drop_table('ai_jobs')
