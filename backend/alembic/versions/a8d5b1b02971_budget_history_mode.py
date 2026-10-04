"""Budget history mode: an imported budget can re-derive every month.

An anchored YNAB import starts its walks at the import month from YNAB's own
figures, which is what keeps it matching the screen the person left. Some
people want IGAB to own the history instead and edit months before the
import, at the cost of that match. `budgets.history_mode` says which:
'anchored' (the default, every budget today) or 'rederived', where the anchor
rows stay but are not read (`import_anchor_repo.ANCHOR_IN_FORCE`).

No data changes: every budget becomes 'anchored', which is how every budget
already behaves. Downgrade drops the column; a re-derived budget is anchored
again, which its untouched anchor rows make exact.

Revision ID: a8d5b1b02971
Revises: 1255a89c2bec
"""

import sqlalchemy as sa
from alembic import op

revision = "a8d5b1b02971"
down_revision = "1255a89c2bec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "budgets",
        sa.Column(
            "history_mode", sa.String(20), server_default=sa.text("'anchored'"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("budgets", "history_mode")
    op.execute("DELETE FROM budget_snapshot_meta")
