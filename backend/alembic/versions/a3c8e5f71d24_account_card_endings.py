"""account card endings

The last four digits of each card that pays from an account, so a receipt
scan can say which account a purchase belongs to. A list per account — a
second cardholder, a replacement card and a phone wallet's device number all
end differently — and unique per budget, so an ending never names two.

Revision ID: a3c8e5f71d24
Revises: c4a1f7e28b63
Create Date: 2026-09-24 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a3c8e5f71d24'
down_revision: Union[str, Sequence[str], None] = 'c4a1f7e28b63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_card_endings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("last4", sa.String(4), nullable=False),
        sa.Column("label", sa.String(60), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("budget_id", "last4", name="uq_card_ending_budget_last4"),
    )
    op.create_index("ix_account_card_endings_budget_id", "account_card_endings", ["budget_id"])
    op.create_index("ix_account_card_endings_account_id", "account_card_endings", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_account_card_endings_account_id", table_name="account_card_endings")
    op.drop_index("ix_account_card_endings_budget_id", table_name="account_card_endings")
    op.drop_table("account_card_endings")
