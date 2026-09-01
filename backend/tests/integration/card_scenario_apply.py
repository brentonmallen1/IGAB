"""A card scenario, applied to a real budget.

The second of three adapters over `sample_budget.card_scenarios` — this one
builds rows and assignments through the ordinary service and factory paths, so
what the integration suite asserts is what the API would actually serve.

Payments go through `create_card_payment`, which goes through the transaction
service: only a paired transfer spends a card's reserve, and any other spelling
is a different scenario wearing this one's clothes.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Budget, BudgetAssignment, Category, CategoryGroup
from igab.sample_budget.card_scenarios import CardScenario
from igab.services.card_payment import ensure_payment_category

from .factories import (
    create_account,
    create_card_payment,
    create_category,
    create_category_group,
    create_transaction,
)


@dataclass
class AppliedScenario:
    scenario: CardScenario
    card_id: uuid.UUID
    payment_category_id: uuid.UUID
    categories: dict[str, Category]


async def _assign(
    session: AsyncSession, budget: Budget, category: Category, month: date, amount
) -> None:
    """Add to a month's assignment rather than insert a second row.

    Several scenarios share Groceries, and a household funds it once a month
    however many cards it charged — `(category_id, month)` is unique, and two
    inserts is not a bigger budget, it is a crash.
    """
    existing = (
        await session.execute(
            select(BudgetAssignment).where(
                BudgetAssignment.category_id == category.id, BudgetAssignment.month == month
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.assigned = existing.assigned + amount
        return
    session.add(
        BudgetAssignment(budget_id=budget.id, category_id=category.id, month=month, assigned=amount)
    )
    await session.flush()


async def _category(
    session: AsyncSession,
    budget: Budget,
    group: CategoryGroup,
    name: str,
    cache: dict[str, Category],
) -> Category:
    if name not in cache:
        cache[name] = await create_category(session, budget, group, name)
    return cache[name]


async def apply_card_scenario(
    session: AsyncSession,
    services,
    budget: Budget,
    scenario: CardScenario,
    anchor: date,
    *,
    cash_account,
    group: CategoryGroup | None = None,
    categories: dict[str, Category] | None = None,
) -> AppliedScenario:
    """Build `scenario` on `budget` and return what it created.

    `cash_account`, `group` and `categories` are passed in so several
    scenarios can share one budget — which is exactly what the demo does, and
    what makes the sample budget and this suite the same fixture.
    """
    group = group or await create_category_group(session, budget, "Everyday")
    cache = categories if categories is not None else {}

    card = await create_account(session, budget, scenario.card, account_type="credit_card")
    await ensure_payment_category(session, card)
    await session.flush()
    payment_category = (
        await session.execute(select(Category).where(Category.linked_account_id == card.id))
    ).scalar_one()

    if scenario.opening:
        # Pre-budget debt is filed NOWHERE. On a card the opening gap is not
        # income — it is a balance the budget never funded, so it reads as
        # Uncovered from the first day rather than as money to assign.
        await create_transaction(
            session,
            budget,
            card,
            scenario.opening,
            scenario.events[0].when.resolve(anchor).replace(day=1),
            memo="Starting balance",
        )

    for event in scenario.events:
        when = event.when.resolve(anchor)
        if event.kind == "fund":
            category = await _category(session, budget, group, event.category or "", cache)
            await _assign(session, budget, category, when.replace(day=1), event.amount)
        elif event.kind == "assign":
            await _assign(session, budget, payment_category, when.replace(day=1), event.amount)
        elif event.kind in ("spend", "refund"):
            category = await _category(session, budget, group, event.category or "", cache)
            amount = -event.amount if event.kind == "spend" else event.amount
            await create_transaction(session, budget, card, amount, when, category=category)
        elif event.kind == "charge":
            # Filed nowhere — `deposit` in the other direction. The row exists
            # on the card and touches no envelope, which is the whole point.
            await create_transaction(session, budget, card, -event.amount, when)
        elif event.kind == "deposit":
            await create_transaction(session, budget, card, event.amount, when)
        elif event.kind == "pay":
            await session.flush()
            await create_card_payment(services, budget, cash_account, card, event.amount, when)
        else:  # pragma: no cover - the guard is the point
            # A kind added to the vocabulary but not here used to produce NO
            # row at all, silently: the scenario's own figures then read as a
            # card nothing had happened to, and only the served layer noticed.
            raise AssertionError(f"card_scenario_apply cannot build a {event.kind!r} event")

    await session.flush()
    return AppliedScenario(
        scenario=scenario,
        card_id=card.id,
        payment_category_id=payment_category.id,
        categories=cache,
    )
