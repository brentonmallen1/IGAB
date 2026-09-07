"""three target types, a funding day, and a weekday for weekly targets

`needed_for_spending` was a fourth target type that computed as one of the
other three: undated it was `monthly_funding` (a flat monthly duty), dated it
was `savings_balance` with a date (reach a balance by then). The editor's copy
could not explain how it differed because it did not. The two UPDATEs below
state the same mapping `domain/targets.py::normalize_legacy_target` states in
Python; a unit test pins the two against each other.

`repeat_frequency` was stored, round-tripped and read by nothing that
computes. Dropped. The downgrade re-adds it empty and cannot recover which
rows were `needed_for_spending`: the mapping is lossy and says so.

`budgets.funding_day` and `category_targets.check_after_day` are the
"pending until this day" rule: before that day of the current month an unmet
target reads pending rather than underfunded, so a household funding across
two paychecks is not shown every envelope red on the 2nd.

`category_targets.weekday` (0=Monday) makes a weekly target mean what it
says: the month's duty is the amount times the number of that weekday in the
month. Existing weekly targets are backfilled to Monday — an arbitrary choice
made visible rather than a null the arithmetic would refuse.

Revision ID: e3b9c7d24a61
Revises: d2f8a5c17b94
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3b9c7d24a61"
down_revision: str | Sequence[str] | None = "d2f8a5c17b94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "budgets",
        sa.Column("funding_day", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_budgets_funding_day", "budgets", "funding_day BETWEEN 1 AND 28"
    )
    op.add_column("category_targets", sa.Column("check_after_day", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_category_targets_check_after_day",
        "category_targets",
        "check_after_day IS NULL OR check_after_day BETWEEN 1 AND 28",
    )
    op.add_column("category_targets", sa.Column("weekday", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_category_targets_weekday",
        "category_targets",
        "weekday IS NULL OR weekday BETWEEN 0 AND 6",
    )
    # The mapping, in the same two cases normalize_legacy_target states.
    op.execute(
        "UPDATE category_targets SET target_type = 'monthly_funding' "
        "WHERE target_type = 'needed_for_spending' AND target_date IS NULL"
    )
    op.execute(
        "UPDATE category_targets SET target_type = 'savings_balance' "
        "WHERE target_type = 'needed_for_spending' AND target_date IS NOT NULL"
    )
    op.execute("UPDATE category_targets SET weekday = 0 WHERE target_type = 'weekly_funding'")
    op.drop_column("category_targets", "repeat_frequency")


def downgrade() -> None:
    op.add_column(
        "category_targets", sa.Column("repeat_frequency", sa.String(20), nullable=True)
    )
    op.drop_constraint("ck_category_targets_weekday", "category_targets", type_="check")
    op.drop_column("category_targets", "weekday")
    op.drop_constraint("ck_category_targets_check_after_day", "category_targets", type_="check")
    op.drop_column("category_targets", "check_after_day")
    op.drop_constraint("ck_budgets_funding_day", "budgets", type_="check")
    op.drop_column("budgets", "funding_day")
