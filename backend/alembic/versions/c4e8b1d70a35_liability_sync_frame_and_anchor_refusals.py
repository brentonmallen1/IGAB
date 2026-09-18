"""liability sync frame and anchor refusals

Three columns behind one defect: a first sync of a mortgage whose servicer
reports the balance in the lender's frame (a debt as a positive number) wrote
an opening balance of roughly twice the loan and then read as paid off.

- accounts.simplefin_sign_frame — which frame this institution speaks,
  decided once and kept (domain/bank_frame.py).
- sync_runs.refused_anchors — opening balances declined as implausible, the
  one outcome the drift check structurally cannot report.
- sync_run_accounts.balance_agrees — whether the bank and the ledger agreed,
  recorded for every account rather than only reconciled ones.

Revision ID: c4e8b1d70a35
Revises: b7f2a91c3d54
Create Date: 2026-09-18 11:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4e8b1d70a35"
down_revision: Union[str, Sequence[str], None] = "b7f2a91c3d54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable on purpose: an account whose frame has never been observed
    # syncs verbatim, which is exactly its behaviour before this column.
    op.add_column("accounts", sa.Column("simplefin_sign_frame", sa.String(length=10), nullable=True))

    op.add_column(
        "sync_runs",
        sa.Column(
            "refused_anchors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("sync_runs", "refused_anchors", server_default=None)

    op.add_column("sync_run_accounts", sa.Column("balance_agrees", sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sync_run_accounts", "balance_agrees")
    op.drop_column("sync_runs", "refused_anchors")
    op.drop_column("accounts", "simplefin_sign_frame")
