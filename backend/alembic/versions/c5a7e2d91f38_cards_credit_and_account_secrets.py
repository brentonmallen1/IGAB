"""card credit limits, credit scores, and encrypted account numbers

Three small things for the accounts side of the house:

- ``liabilities.credit_limit`` — the issuer's limit on a card, so utilization
  (balance ÷ limit, domain/credit.py) can be shown and the Guide can say
  when a card is carrying more than 30% of it. Null when unknown; SimpleFIN
  does not carry it.
- ``credit_scores`` — scores the person typed in, by date and bureau, for
  the Guide's credit-score tool. Manual on purpose; there is no API worth a
  household integrating.
- ``accounts.account_number_encrypted`` / ``routing_number_encrypted`` /
  ``account_number_last4`` — reference numbers encrypted at rest with the
  same Fernet key bank sync uses. The last four stay in the clear for the
  masked display.

Revision ID: c5a7e2d91f38
Revises: b8e5d1c73a49
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c5a7e2d91f38"
down_revision: str | Sequence[str] | None = "b8e5d1c73a49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("liabilities", sa.Column("credit_limit", sa.Numeric(19, 4), nullable=True))
    op.add_column("accounts", sa.Column("account_number_encrypted", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("routing_number_encrypted", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("account_number_last4", sa.String(4), nullable=True))
    op.create_table(
        "credit_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("budget_id", UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_on", sa.Date(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("bureau", sa.String(40), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("budget_id", "recorded_on", "bureau", name="uq_credit_score_day_bureau"),
    )
    op.create_index("ix_credit_scores_budget_id", "credit_scores", ["budget_id"])


def downgrade() -> None:
    op.drop_index("ix_credit_scores_budget_id", table_name="credit_scores")
    op.drop_table("credit_scores")
    op.drop_column("accounts", "account_number_last4")
    op.drop_column("accounts", "routing_number_encrypted")
    op.drop_column("accounts", "account_number_encrypted")
    op.drop_column("liabilities", "credit_limit")
