"""liability payment composition

What a monthly debt payment is made of beside principal and interest —
escrowed tax, insurance, PMI, HOA. Optional: NULL means "no composition on
file", which is every debt that is not an escrowed mortgage, so there is
nothing to backfill and no default to invent.

Nullable rather than an empty-list default on purpose. "Never said" and "said
there is nothing" read the same in a list and differently to a person, and the
page only offers to explain the composition when one exists.

Revision ID: 86124882b15f
Revises: a3c8e5b17f42
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "86124882b15f"
down_revision: str | Sequence[str] | None = "a3c8e5b17f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "liabilities",
        sa.Column("payment_components", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("liabilities", "payment_components")
