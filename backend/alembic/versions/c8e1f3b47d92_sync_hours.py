"""sync_hours: a bank connection can sync more than once a day

A connection carried `daily_sync_time` — one time, once a day — and
`sync_interval_hours`, which was on the model and in both schemas and which
nothing ever read. Neither could express "at 07:00 and again at 19:00", and
two fields that both claim to say when a sync runs are one drift away from
disagreeing.

They are replaced by a single list of UTC hours. "Every 4 hours" and "at 7
and 19" are both just lists, so the scheduler has one question to ask, and the
UI's two ways of authoring a schedule write the same field. Empty = never.

The old time is carried across as a one-element list, so an existing schedule
keeps running at the hour it always did.

Revision ID: c8e1f3b47d92
Revises: b6d4e8a20c73
Create Date: 2026-08-28 22:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c8e1f3b47d92"
down_revision: str | Sequence[str] | None = "b6d4e8a20c73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "simplefin_connections",
        sa.Column(
            "sync_hours",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    # Carry the existing schedule over unchanged: the hour it ran at becomes
    # the one hour in the list.
    op.execute(
        """
        UPDATE simplefin_connections
           SET sync_hours = jsonb_build_array(EXTRACT(HOUR FROM daily_sync_time)::int)
         WHERE daily_sync_time IS NOT NULL
        """
    )
    op.drop_column("simplefin_connections", "daily_sync_time")
    op.drop_column("simplefin_connections", "sync_interval_hours")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "simplefin_connections",
        sa.Column("sync_interval_hours", sa.Integer(), nullable=False, server_default="24"),
    )
    op.add_column(
        "simplefin_connections",
        sa.Column("daily_sync_time", sa.Time(), nullable=True),
    )
    # Only the first hour survives going back — the old column cannot hold
    # more than one, which is the whole reason for this migration.
    op.execute(
        """
        UPDATE simplefin_connections
           SET daily_sync_time = make_time((sync_hours->>0)::int, 0, 0)
         WHERE jsonb_array_length(sync_hours) > 0
        """
    )
    op.drop_column("simplefin_connections", "sync_hours")
