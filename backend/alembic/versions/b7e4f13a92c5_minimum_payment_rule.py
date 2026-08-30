"""a minimum payment can be a rule, not only a number

Every existing row becomes kind='fixed' with its stored amount, which is what
it already meant. Nothing anyone has already seen changes: a fixed rule
reproduces today's schedules exactly, and the unit tests that pinned them run
unchanged.

Revision ID: b7e4f13a92c5
Revises: d9f2a4c61e08
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4f13a92c5"
down_revision: str | Sequence[str] | None = "d9f2a4c61e08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "liabilities",
        sa.Column(
            "minimum_payment_kind",
            sa.String(length=20),
            nullable=False,
            server_default="fixed",
        ),
    )
    op.add_column(
        "liabilities",
        sa.Column("minimum_payment_percent", sa.Numeric(precision=6, scale=4), nullable=True),
    )
    op.add_column(
        "liabilities",
        sa.Column("minimum_payment_floor", sa.Numeric(precision=19, scale=4), nullable=True),
    )
    op.add_column(
        "liabilities",
        sa.Column(
            "minimum_payment_plus_interest",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    # A percent rule has nowhere to go in the old shape. Dropping the columns
    # leaves `minimum_payment` — which for a percent rule is NULL — so a
    # downgraded row reads as "no minimum entered" rather than as a wrong
    # number. Blank is recoverable; a plausible wrong figure is not.
    op.drop_column("liabilities", "minimum_payment_plus_interest")
    op.drop_column("liabilities", "minimum_payment_floor")
    op.drop_column("liabilities", "minimum_payment_percent")
    op.drop_column("liabilities", "minimum_payment_kind")
