"""The card's set-aside envelope — guaranteed by construction, like a
liability companion.

The credit model (domain/cards.py) needs somewhere for a card's assignments
to live: one Category per card, linked via `linked_account_id`. This module
is the one writer of that link. The category is invisible as an envelope —
the grid does not draw it and no picker offers it, because both
`IS_CATEGORIZABLE` and `IS_ASSIGNABLE` name `LINKED_TO_CARD` outright
(they leant on the group being hidden until 2026-08-29, which is a
coincidence, not a rule) — and the budget page's card section is its only
face. Its *assignments* are real BudgetAssignment rows, so moving money to
a card is the same operation as moving money anywhere, undo included.

Nothing may be *filed* here: the budget summary computes this envelope's
balance from card arithmetic and overwrites whatever its transaction sums say,
so a row filed to it is money that leaves the budget with no red anywhere to
explain it. `services/filing.require_categorizable` is what enforces that now
— it reads `IS_CATEGORIZABLE`, which already names `LINKED_TO_CARD`, so the
card case is one branch of the whole rule rather than the only third of it the
server checked.

Mirrors `liability_service.ensure_for_account`: idempotent, adopts a
soft-deleted row rather than inserting beside it, returns None when there
was nothing to do so callers can fire and forget.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Category, CategoryGroup

#: One group holds every card's envelope. Not system — a system group means
#: income, which is how `activity_class` reads it — and **not archived**: the
#: group is live and in daily use, and the archived listing is the user's own
#: envelopes, not the app's plumbing.
#:
#: It was created archived (as `is_hidden`) until the rename, because that flag
#: was the only thing keeping card envelopes out of the move-money picker.
#: `IS_ASSIGNABLE` now names `LINKED_TO_CARD` outright, so the concealment does
#: not need a flag that also means something to the user. The migration
#: repairs existing budgets, matching on shape rather than on this name.
CARD_PAYMENTS_GROUP = "Credit Card Payments"


def is_card_account(account: Account) -> bool:
    """The Python twin of txn_filters.CARD_ACCOUNT — one definition per side,
    both spelling `classification == 'liability' AND on_budget`."""
    return account.on_budget and account.classification == "liability"


async def ensure_payment_category(session: AsyncSession, account: Account) -> Category | None:
    """Guarantee the linked category for a card account.

    Returns the category it created or revived, None when there was nothing
    to do — the account is not a card, or its envelope already stands.
    """
    if account.is_deleted or not is_card_account(account):
        return None

    existing = (
        await session.execute(select(Category).where(Category.linked_account_id == account.id))
    ).scalar_one_or_none()
    if existing is not None:
        if not existing.is_deleted:
            return None
        existing.is_deleted = False
        await session.flush()
        return existing

    group = await _ensure_group(session, account.budget_id)
    category = Category(
        budget_id=account.budget_id,
        category_group_id=group.id,
        name=account.name,
        linked_account_id=account.id,
    )
    session.add(category)
    await session.flush()
    return category


async def _ensure_group(session: AsyncSession, budget_id: uuid.UUID) -> CategoryGroup:
    existing = (
        await session.execute(
            select(CategoryGroup).where(
                CategoryGroup.budget_id == budget_id,
                CategoryGroup.name == CARD_PAYMENTS_GROUP,
                CategoryGroup.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    group = CategoryGroup(budget_id=budget_id, name=CARD_PAYMENTS_GROUP)
    session.add(group)
    await session.flush()
    return group
