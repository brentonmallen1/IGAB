"""Import plan months: YNAB's own figures for every month of an import.

A YNAB import kept one month of the export's Plan figures — the anchor's
B−1 — and dropped the rest as advisory. Looking back before the import month
then had nothing honest to show: re-deriving those months is exactly the
drift the anchor exists to retire. `import_plan_months` keeps every Plan.csv
row as exported (Assigned, Activity, Available, YNAB's display order), so the
Budget page can show earlier months read-only, as YNAB had them.

Written only by imports from here on. No backfill: an older import never
stored these figures and cannot recover them, so it keeps today's behaviour
(the month view stops at the import month) until it is re-imported.

Revision ID: f49967af8129
Revises: a8d5b1b02971
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f49967af8129"
down_revision = "a8d5b1b02971"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_plan_months",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("category_group", sa.String(255), nullable=False),
        sa.Column("category", sa.String(255), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("income", sa.Boolean(), nullable=False),
        sa.Column("assigned", sa.Numeric(19, 4), nullable=False),
        sa.Column("activity", sa.Numeric(19, 4), nullable=True),
        sa.Column("available", sa.Numeric(19, 4), nullable=True),
    )
    op.create_index(
        "ix_import_plan_months_budget_month", "import_plan_months", ["budget_id", "month"]
    )


def downgrade() -> None:
    op.drop_index("ix_import_plan_months_budget_month", table_name="import_plan_months")
    op.drop_table("import_plan_months")
