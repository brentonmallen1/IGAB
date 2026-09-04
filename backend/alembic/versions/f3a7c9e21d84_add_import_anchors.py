"""add import anchors

One table behind full-position anchoring of YNAB imports: YNAB's own
displayed position at the boundary month (per-category Available, per-card
CCP Available and uncovered debt), written once by the importer so the
envelope and card walks start from it instead of re-deriving pre-anchor
history.

Revision ID: f3a7c9e21d84
Revises: b5d2f8c41a97
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a7c9e21d84"
down_revision: Union[str, Sequence[str], None] = "b5d2f8c41a97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_anchors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(category_id IS NULL) != (account_id IS NULL)",
            name="ck_import_anchor_one_target",
        ),
    )
    op.create_index("ix_import_anchors_budget_id", "import_anchors", ["budget_id"])
    op.create_index("ix_import_anchors_category_id", "import_anchors", ["category_id"])
    op.create_index("ix_import_anchors_account_id", "import_anchors", ["account_id"])


def downgrade() -> None:
    # Dropping the anchors turns an anchored budget back into a full-history
    # walk: envelope and card figures will re-derive from day one and will
    # no longer match YNAB's displayed position at the import boundary.
    op.drop_index("ix_import_anchors_account_id", table_name="import_anchors")
    op.drop_index("ix_import_anchors_category_id", table_name="import_anchors")
    op.drop_index("ix_import_anchors_budget_id", table_name="import_anchors")
    op.drop_table("import_anchors")
