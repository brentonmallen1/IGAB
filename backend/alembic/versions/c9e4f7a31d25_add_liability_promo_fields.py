"""add_liability_promo_fields

Promotional / deadline financing: interest_rate applies only after
promo_end_date (0% during the promo window), and promo_deferred_interest
marks retailer deals that charge interest retroactively when the balance
isn't cleared by the deadline. term_months records an explicitly known
contractual term (otherwise the UI shows the term implied by origination +
principal + minimum payment).

Revision ID: c9e4f7a31d25
Revises: a4d7e2c96b18
Create Date: 2026-08-20 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e4f7a31d25"
down_revision: Union[str, Sequence[str], None] = "a4d7e2c96b18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("liabilities", sa.Column("promo_end_date", sa.Date(), nullable=True))
    op.add_column(
        "liabilities",
        sa.Column(
            "promo_deferred_interest", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column("liabilities", sa.Column("term_months", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("liabilities", "term_months")
    op.drop_column("liabilities", "promo_deferred_interest")
    op.drop_column("liabilities", "promo_end_date")
