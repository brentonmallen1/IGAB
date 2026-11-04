"""Snapshot meta generation: which rebuild a budget's snapshots are valid from.

`budget_snapshot_meta` said only *whether* a budget's category snapshots are
valid. The card walk is now cached in process on the same signal
(`igab.services.walk_cache`), and an in-process entry has to know *which*
rebuild it was computed under — presence alone would let an entry from before
an invalidation match the row the next rebuild writes.

Every existing row gets a fresh value, which is correct: no process holds an
entry yet. No snapshot is invalidated and no figure moves.

Revision ID: d7a3f9e2c614
Revises: b5e2c8d41a73
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d7a3f9e2c614"
down_revision = "b5e2c8d41a73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "budget_snapshot_meta",
        sa.Column(
            "generation",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("budget_snapshot_meta", "generation")
