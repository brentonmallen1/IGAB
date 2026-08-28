"""budget_import_summary

What a YNAB import decided used to exist only as a stack of up to six toasts,
fired while the app was mid-route-change, and then it was gone: the parity
check against the export's own figures, which plan rows were skipped, which
categories were auto-tagged, and up to fifty per-row errors of which the UI
showed one. None of it is recoverable from the resulting budget.

Store it on the budget. A YNAB import always creates exactly one budget (the
route 409s on a name clash), so the relationship is 1:1 and a table of its own
would buy nothing. JSONB rather than typed columns because this is a record of
an event, not queryable state.

`import_reviewed_at` is what makes the review open by itself exactly once.
Null on every existing row, so budgets imported before this will offer their
review the first time they are opened -- which is the point: those are the
budgets with no tags at all.

Revision ID: a7c3e91d5f42
Revises: f4a1c7e29b56
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7c3e91d5f42'
down_revision: Union[str, Sequence[str], None] = 'f4a1c7e29b56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "budgets",
        sa.Column("import_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "budgets",
        sa.Column("import_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("budgets", "import_reviewed_at")
    op.drop_column("budgets", "import_summary")
