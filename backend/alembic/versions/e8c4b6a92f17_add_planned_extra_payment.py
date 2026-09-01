"""Liability.planned_extra_payment — a standing curtailment plan

Revision ID: e8c4b6a92f17
Revises: d7f3a9c15e82
Create Date: 2026-09-01

What the household intends to pay each month above the minimum. All principal
by construction (interest is a function of balance and time), so no split is
stored — just the monthly figure the paydown page's what-if used to demand be
retyped every visit.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8c4b6a92f17"
down_revision: Union[str, Sequence[str], None] = "d7f3a9c15e82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "liabilities", sa.Column("planned_extra_payment", sa.Numeric(19, 4), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("liabilities", "planned_extra_payment")
