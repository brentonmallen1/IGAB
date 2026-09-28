"""The card's envelope — guaranteed by construction, like a
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

from sqlalchemy import func, select
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

#: The budget's one envelope for card interest and fees, found by this key
#: (`Category.system_key`), never by its name — the user may rename it.
#:
#: Interest and a late fee are spending nobody chose, and before this they had
#: nowhere good to go: a transfer is wrong (no money moved), and the card's own
#: envelope refuses filing on purpose (`filing.require_categorizable`), because
#: card arithmetic overwrites it. YNAB's answer is an ordinary spending
#: envelope, and so is this one — fundable, assignable, categorizable, able to
#: go red, counted in every total and report. What sets it apart is only where
#: it is drawn: in the Credit cards section, beside the cards that charge it
#: (`category_filters.CARD_SECTION_CATEGORY`). One per budget, shared by every
#: card; the register row's account already says which card charged it.
CARD_INTEREST_KEY = "card_interest"
#: What it is called when the app makes it. A name only: after that it is
#: found by `CARD_INTEREST_KEY`.
CARD_INTEREST_NAME = "Interest & fees"
#: Names an existing envelope in the card group may already carry, adopted
#: rather than collided with (case-insensitive). A user who made their own
#: before this existed keeps it, with its money and history.
_ADOPTABLE_INTEREST_NAMES = ("interest & fees", "interest and fees")


def names_interest_envelope(name: str, current: str | None = None) -> bool:
    """Does a card-group category called `name` mean Interest & fees?

    The adoptable spellings, or the envelope's `current` name when it has
    been renamed. For the YNAB-format import, which otherwise reads every
    "Credit Card Payments" entry as a card's reserve: IGAB's own export files
    interest there too, and a round trip would strip it.
    """
    folded = name.strip().lower()
    return folded in _ADOPTABLE_INTEREST_NAMES or (
        current is not None and folded == current.strip().lower()
    )


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

    # Every card path, not only the one that creates the card's envelope: a
    # budget whose card envelopes the showcase spec or an import placed in a
    # group of their own still has cards, and so still needs somewhere to file
    # their interest.
    await ensure_interest_envelope(session, account.budget_id)

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


async def find_interest_envelope(session: AsyncSession, budget_id: uuid.UUID) -> Category | None:
    """The budget's live Interest & fees envelope, archived or not, by key."""
    return (
        await session.execute(
            select(Category).where(
                Category.budget_id == budget_id,
                Category.system_key == CARD_INTEREST_KEY,
                Category.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()


async def ensure_interest_envelope(session: AsyncSession, budget_id: uuid.UUID) -> Category:
    """Guarantee the budget's Interest & fees envelope, and return it.

    Idempotent, in this order:

    1. the keyed envelope, wherever it now lives and whatever it is called;
    2. otherwise a live, unkeyed "Interest & fees" (or "and fees") already in
       the card group, which is stamped with the key — creating a second one
       beside it would collide on the name, and ignoring it would leave the
       user's own envelope unfound;
    3. otherwise a new "Interest & fees" at the end of the card group.

    Never un-archives: an envelope the user archived stays archived, and the
    cards section then draws nothing for it.

    Not recorded in the change log, for the reason its group is not: it is
    budget-level plumbing shared by every card, not something the first card
    owns, so undoing that card must not take it — a later card's interest may
    already be filed there.
    """
    # Imported here: `category_filters` reads `CARD_INTEREST_KEY` from this
    # module, and the repository imports `category_filters`.
    from igab.repositories.category_repo import CategoryRepository

    existing = await find_interest_envelope(session, budget_id)
    if existing is not None:
        return existing

    group = await _ensure_group(session, budget_id)
    adoptable = (
        (
            await session.execute(
                select(Category)
                .where(
                    Category.category_group_id == group.id,
                    Category.system_key.is_(None),
                    Category.linked_account_id.is_(None),
                    Category.linked_liability_id.is_(None),
                    Category.is_deleted == False,  # noqa: E712
                    # The same folding `names_interest_envelope` applies.
                    func.lower(func.trim(Category.name)).in_(_ADOPTABLE_INTEREST_NAMES),
                )
                .order_by(Category.sort_order, Category.created_at)
            )
        )
        .scalars()
        .first()
    )
    if adoptable is not None:
        adoptable.system_key = CARD_INTEREST_KEY
        await session.flush()
        return adoptable

    envelope = Category(
        budget_id=budget_id,
        category_group_id=group.id,
        name=CARD_INTEREST_NAME,
        system_key=CARD_INTEREST_KEY,
        # Last in the group — the one rule for a new row's position.
        sort_order=await CategoryRepository(session).next_sort_order(group.id),
    )
    session.add(envelope)
    await session.flush()
    return envelope


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
