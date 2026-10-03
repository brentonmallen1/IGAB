"""sync runs record anchors skipped for history

A first sync no longer writes an opening balance on an account that already
held rows from before the fetch window — a YNAB migration, history typed by
hand. The run says so, one sentence per account, and the sync log reads it
back. Its own column rather than a share of `refused_anchors`, because a
refusal degrades the run and a skip is only informational.

Revision ID: d81f4c2a6b09
Revises: 2cb769068102
Create Date: 2026-10-01 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d81f4c2a6b09"
down_revision: Union[str, Sequence[str], None] = "2cb769068102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "sync_runs",
        sa.Column(
            "anchors_skipped_for_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("sync_runs", "anchors_skipped_for_history", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sync_runs", "anchors_skipped_for_history")
