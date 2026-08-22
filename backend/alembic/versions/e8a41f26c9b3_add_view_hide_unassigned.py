"""add hide_unassigned to budget views

Revision ID: e8a41f26c9b3
Revises: d5b93c1e740a
Create Date: 2026-08-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8a41f26c9b3"
down_revision: Union[str, Sequence[str], None] = "d5b93c1e740a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Whether a view drops the categories it hasn't placed.

    Default false, matching the existing behaviour: unplaced categories collect
    under "Unassigned" so a category added after the view was built surfaces
    rather than vanishing. Users who know a view is complete can opt into the
    tidier reading.
    """
    op.add_column(
        "budget_views",
        sa.Column(
            "hide_unassigned", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("budget_views", "hide_unassigned")
