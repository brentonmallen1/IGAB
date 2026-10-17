"""sync runs record the rows the bank no longer reports

A sync that removed a pending hold the bank had dropped said only
`removed_pending = 1`, and nothing showed even that. Each run now records
every linked row it found missing from the feed — the hold it removed, or
the row it kept — with enough to list it and to restore it.

Revision ID: a4e7c2d9b1f3
Revises: f49967af8129
Create Date: 2026-10-17 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a4e7c2d9b1f3"
down_revision: Union[str, Sequence[str], None] = "f49967af8129"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "sync_runs",
        sa.Column(
            "no_longer_reported",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("sync_runs", "no_longer_reported", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sync_runs", "no_longer_reported")
