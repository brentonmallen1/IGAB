"""The two rules every path that creates a budget has to follow.

There are four such paths now — create, create-sample, import-from-YNAB, and
import-from-snapshot — and the last one lives in a service rather than a
router, so these could not stay private to ``api/v1/budgets.py``.

Both rules are small and both are load-bearing: a budget with no owner row is
invisible even to the person who just made it, and a colliding name is a 409
in the middle of an import that has already read a 25 MB file.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Budget, BudgetMember


def grant_owner(session: AsyncSession, budget_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Every budget-creation path must call this: membership is the
    authorization source of truth, and a budget without an owner row would be
    invisible even to its creator."""
    session.add(BudgetMember(budget_id=budget_id, user_id=user_id, role="owner"))


async def unique_budget_name(session: AsyncSession, user_id: uuid.UUID, base: str) -> str:
    """``base``, or the first free "base 2", "base 3", … for this user.

    ``uq_budget_user_name`` is per user, so this is checked per user. Importing
    a snapshot of a budget you already have is the ordinary case — that is what
    "duplicate this budget to experiment against" *is* — so a collision must
    resolve rather than fail.
    """
    existing = await session.execute(select(Budget.name).where(Budget.user_id == user_id))
    taken = {name.lower() for (name,) in existing}
    name = base
    suffix = 2
    while name.lower() in taken:
        name = f"{base} {suffix}"
        suffix += 1
    return name
