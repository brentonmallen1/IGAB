"""make liability interest_rate and minimum_payment nullable

Revision ID: a3f7c1d84e26
Revises: e8a41f26c9b3
Create Date: 2026-08-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f7c1d84e26"
down_revision: Union[str, Sequence[str], None] = "e8a41f26c9b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Terms become optional so a liability can exist before they are known.

    The prerequisite for creating a companion liability alongside every
    liability-classified account: such a row has no APR and no minimum payment
    until someone fills them in. Zero defaults are not an option — at zero,
    `amortization_schedule` hits `payment <= interest` on the first iteration
    and reports `never_pays_off=True`, which rides into the Liabilities report's
    interest total. "Not known" has to be representable as absent, not as zero.

    No data change: every existing row keeps its values.
    """
    op.alter_column("liabilities", "interest_rate", existing_type=sa.Numeric(7, 4), nullable=True)
    op.alter_column(
        "liabilities", "minimum_payment", existing_type=sa.Numeric(19, 4), nullable=True
    )


def downgrade() -> None:
    """Restore NOT NULL, filling unset terms with zero.

    Zero is the only value available — there is nothing truthful to invent —
    and it reproduces the pre-migration model exactly, including its
    `never_pays_off` behaviour for a row whose terms were never set. Rows are
    filled rather than deleted: a companion liability may already carry
    snapshots or a linked category by the time anyone downgrades.
    """
    op.execute("UPDATE liabilities SET interest_rate = 0 WHERE interest_rate IS NULL")
    op.execute("UPDATE liabilities SET minimum_payment = 0 WHERE minimum_payment IS NULL")
    op.alter_column("liabilities", "interest_rate", existing_type=sa.Numeric(7, 4), nullable=False)
    op.alter_column(
        "liabilities", "minimum_payment", existing_type=sa.Numeric(19, 4), nullable=False
    )
