"""Record when the bank computed the balance it reported.

The bridge ships `balance-date` beside every balance and IGAB dropped it, so
the stored figure read as live. A bridge running behind the bank then made
ordinary spending look like missing rows, and the account page told the user
to refetch 90 days to find transactions that were never absent. Nullable:
every account predating this column has no date, and no date means the
staleness question simply is not asked.

Revision ID: b3f70c5e12d9
Revises: aab17f2376dc
"""

import sqlalchemy as sa
from alembic import op

revision = "b3f70c5e12d9"
down_revision = "aab17f2376dc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("simplefin_balance_date", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accounts", "simplefin_balance_date")
