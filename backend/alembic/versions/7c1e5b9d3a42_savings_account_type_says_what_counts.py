"""the savings account type says what counts

The built-in Savings account type's description advised "Tag a category as
Savings if you want it counted" for money moved into an on-budget savings
account. That cannot be done: a transfer between two on-budget accounts carries
no category. The description now says the two things that work — keep savings
in Savings envelopes set to kept here, or take the account off budget and turn
on Counts as savings — matching `domain/account_types.py`.

Only a system row still carrying the old wording is rewritten, so a budget
that edited its own description keeps it. Frozen SQL with the text inlined
(precedent e3f1a8c5d920).

Revision ID: 7c1e5b9d3a42
Revises: e52d44b73edb
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c1e5b9d3a42"
down_revision: str | Sequence[str] | None = "e52d44b73edb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = (
    "Money set aside but still yours to plan with. On budget so it can "
    "back envelopes like an emergency fund. Because it is on budget, "
    "moving money here is not counted as saving — the money never left "
    "your budget. Tag a category as Savings if you want it counted."
)
_NEW = (
    "Money set aside but still yours to plan with. On budget so it can "
    "back envelopes like an emergency fund. Because it is on budget, "
    "moving money here is not counted as saving — the money never left "
    "your budget, and your envelopes say what it is for: keep savings in "
    "Savings envelopes set to kept here. To count the account itself, "
    "take it off budget and turn on Counts as savings."
)


def _swap(old: str, new: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE account_types SET description = :new "
            "WHERE key = 'savings' AND is_system = true AND description = :old"
        ),
        {"old": old, "new": new},
    )


def upgrade() -> None:
    _swap(_OLD, _NEW)


def downgrade() -> None:
    _swap(_NEW, _OLD)
