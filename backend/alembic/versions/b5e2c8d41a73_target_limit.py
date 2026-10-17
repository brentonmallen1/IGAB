"""Target limit: an optional "Stop at $L" on monthly and weekly targets.

A monthly (or weekly) target asked for its rate every month forever, so an
envelope meant to hold a fixed buffer — fill $100 a month until it holds
$1,000 — read underfunded once it was full. `target_limit` caps it: the month
asks for the rate only while the balance carried in is short of L, and an
envelope holding L reads funded.

Nullable, and NULL on every existing row: no target changes meaning.

Revision ID: b5e2c8d41a73
Revises: a4e7c2d9b1f3
"""

import sqlalchemy as sa
from alembic import op

revision = "b5e2c8d41a73"
down_revision = "a4e7c2d9b1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("category_targets", sa.Column("target_limit", sa.Numeric(19, 4), nullable=True))
    op.create_check_constraint(
        "ck_category_targets_limit",
        "category_targets",
        "target_limit IS NULL OR (target_limit > 0"
        " AND target_type IN ('monthly_funding', 'weekly_funding'))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_category_targets_limit", "category_targets", type_="check")
    op.drop_column("category_targets", "target_limit")
