"""Assets: a valued thing, its dated value points, and the debt link

Revision ID: d7f3a9c15e82
Revises: c4e8b2a71d59
Create Date: 2026-09-01

A first-class Asset — worth stated and dated, never derived from a ledger —
mirroring the unmanaged-liability pair (`liabilities.manual_balance` +
`liability_balance_snapshots`). `liabilities.linked_asset_id` is deliberately
NOT unique: a house can secure a mortgage and a HELOC, and equity is
value − Σ owed across everything linked.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d7f3a9c15e82"
down_revision: Union[str, Sequence[str], None] = "c4e8b2a71d59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("asset_type", sa.String(30), nullable=True),
        sa.Column("manual_value", sa.Numeric(19, 4), nullable=True),
        sa.Column("value_as_of", sa.Date(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_assets_budget_id", "assets", ["budget_id"])

    op.create_table(
        "asset_value_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(19, 4), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("asset_id", "date", name="uq_asset_value_date"),
    )
    op.create_index("ix_asset_value_snapshots_asset_id", "asset_value_snapshots", ["asset_id"])

    op.add_column(
        "liabilities",
        sa.Column(
            "linked_asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_liabilities_linked_asset_id", "liabilities", ["linked_asset_id"])


def downgrade() -> None:
    op.drop_index("ix_liabilities_linked_asset_id", table_name="liabilities")
    op.drop_column("liabilities", "linked_asset_id")
    op.drop_index("ix_asset_value_snapshots_asset_id", table_name="asset_value_snapshots")
    op.drop_table("asset_value_snapshots")
    op.drop_index("ix_assets_budget_id", table_name="assets")
    op.drop_table("assets")
