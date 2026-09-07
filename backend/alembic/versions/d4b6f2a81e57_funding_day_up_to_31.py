"""Funding day may be any day of the month, not just one every month has

The bound was 1..28 because `is_pending` compared `today.day < effective_day`
with no clamp: a day of 30 never arrives in February, so the target would read
"pending" for the whole month and never nag. The cap was guarding an unclamped
comparison from the outside.

`is_pending` now clamps to the month's real length, so "check after the 31st"
means the 31st, or the last day of a month that has no 31st. 28 is a strange
thing to have to explain to someone who is paid on the 30th.

Revision ID: d4b6f2a81e57
Revises: c5a7e2d91f38
Create Date: 2026-09-07

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4b6f2a81e57"
down_revision: str | None = "c5a7e2d91f38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_budgets_funding_day", "budgets", type_="check")
    op.create_check_constraint("ck_budgets_funding_day", "budgets", "funding_day BETWEEN 1 AND 31")

    op.drop_constraint(
        "ck_category_targets_check_after_day", "category_targets", type_="check"
    )
    op.create_check_constraint(
        "ck_category_targets_check_after_day",
        "category_targets",
        "check_after_day IS NULL OR check_after_day BETWEEN 1 AND 31",
    )


def downgrade() -> None:
    """Lossy: a day above 28 has to become one, and 28 is the honest choice —
    it is the last day every month has, which is what the old bound meant."""
    op.execute("UPDATE budgets SET funding_day = 28 WHERE funding_day > 28")
    op.execute(
        "UPDATE category_targets SET check_after_day = 28 WHERE check_after_day > 28"
    )
    op.drop_constraint("ck_budgets_funding_day", "budgets", type_="check")
    op.create_check_constraint("ck_budgets_funding_day", "budgets", "funding_day BETWEEN 1 AND 28")
    op.drop_constraint(
        "ck_category_targets_check_after_day", "category_targets", type_="check"
    )
    op.create_check_constraint(
        "ck_category_targets_check_after_day",
        "category_targets",
        "check_after_day IS NULL OR check_after_day BETWEEN 1 AND 28",
    )
