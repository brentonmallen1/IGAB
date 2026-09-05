"""card payment due day

Revision ID: e7c3a5f18d92
Revises: d4b7f2a91c36
Create Date: 2026-09-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7c3a5f18d92"
down_revision: Union[str, Sequence[str], None] = "d4b7f2a91c36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The card bill's due day of the month — statement metadata, nullable.

    No backfill and no default: nobody has told us a due day yet, and a blank
    reads as "not set" rather than a guessed 1st.
    """
    op.add_column("liabilities", sa.Column("payment_due_day", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("liabilities", "payment_due_day")
