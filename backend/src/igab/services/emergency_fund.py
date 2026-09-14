"""The emergency fund — the one home of the figure and what it counted.

**Chosen, never guessed.** The fund is exactly three things:

- the envelopes tagged Emergency fund (`category_filters.IN_EMERGENCY_FUND`),
  at the Budget page's Available for the current month;
- the off-budget accounts marked "counts toward emergency fund"
  (`txn_filters.EMERGENCY_FUND_ACCOUNT`), at their balance;
- anything declared as kept elsewhere — the Guide's `external` binding rows
  (`guide.bindings.resolve`).

It used to be guessed. `GuideDetection.emergency_fund` looked for a category
whose name said "emergency", "rainy day" or "buffer", fell back to every
account of type `savings`, and picked whichever found money — so a house
deposit in a savings account could be reported as a household's emergency
fund, and nothing on screen said which it had picked. Three readers then folded
that guess with the declared amount on their own (the Guide signal,
`report_basics.emergency_fund`, and the coverage report's `fund_entities` /
`_fund_balance_at`). They now all read this module.

**The savings mode does not move the total.** An Emergency fund envelope set to
sent out counts its outflows as saved on the savings RATE; the fund is what is
still set aside, so its not-yet-sent Available counts here either way.

**Dismissing the Guide concept hides the Guide's step, not the fund.** The
reports show what was chosen whatever the Guide tracks: the tags and the account
flags are budget facts, not Guide answers.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Category
from igab.domain.dates import month_end, month_start
from igab.domain.money import quantize_cents
from igab.guide.bindings import fold_external, resolve
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_filters import IN_EMERGENCY_FUND
from igab.repositories.txn_filters import EMERGENCY_FUND_ACCOUNT

if TYPE_CHECKING:
    from igab.services.budget_service import BudgetService

ZERO = Decimal("0")

#: The Guide concept whose `external` rows are the "kept elsewhere" part.
CONCEPT_KEY = "emergency_fund"


@dataclass(frozen=True)
class FundPart:
    """One envelope or account the fund counted, and what it holds."""

    id: uuid.UUID
    name: str
    balance: Decimal


@dataclass(frozen=True)
class FundExternal:
    """What the household said it keeps outside IGAB.

    `declared` without an `amount` is "I have this covered" — a complete
    answer, and never read as zero.
    """

    declared: bool
    amount: Decimal | None
    as_of: date | None
    note: str | None


@dataclass(frozen=True)
class EmergencyFund:
    categories: tuple[FundPart, ...]
    accounts: tuple[FundPart, ...]
    external: FundExternal
    #: Parts plus the declared amount (`fold_external`). None only when there
    #: are no parts and no declared figure.
    total: Decimal | None
    #: Anything chosen at all: an envelope, an account, or a declaration.
    set_up: bool

    @property
    def parts(self) -> tuple[FundPart, ...]:
        return self.categories + self.accounts

    @property
    def in_budget(self) -> Decimal | None:
        """What IGAB can see — the parts, without the declared amount. None
        when nothing in IGAB was chosen."""
        return _parts_total(self.parts)

    @property
    def draws_history(self) -> bool:
        """Whether a month-by-month line means anything: a part to walk, or a
        declared figure to carry. A declaration with no figure draws nothing."""
        return bool(self.parts) or self.external.amount is not None

    @property
    def source(self) -> str | None:
        """A short description of what was counted, or None when nothing was.

        "Emergency Fund, Harborstone Reserve and an amount kept elsewhere".
        """
        names = [p.name for p in self.parts]
        if self.external.declared:
            names.append("an amount kept elsewhere")
        if not names:
            return None
        if len(names) == 1:
            return names[0]
        return f"{', '.join(names[:-1])} and {names[-1]}"


def _parts_total(parts: Sequence[FundPart]) -> Decimal | None:
    if not parts:
        return None
    return quantize_cents(sum((p.balance for p in parts), ZERO))


def _service(session: AsyncSession, budget_service: BudgetService | None) -> BudgetService:
    if budget_service is not None:
        return budget_service
    # Lazily: guide.detection imports this module's readers at import time.
    from igab.guide.detection import budget_service_from

    return budget_service_from(session)


async def _chosen(
    session: AsyncSession, budget_id: uuid.UUID
) -> tuple[list[tuple[uuid.UUID, str]], list[tuple[uuid.UUID, str]]]:
    """(envelopes, accounts) the household chose, by name."""
    categories = (
        await session.execute(
            select(Category.id, Category.name)
            .where(Category.budget_id == budget_id, IN_EMERGENCY_FUND)
            .order_by(Category.name, Category.id)
        )
    ).all()
    accounts = (
        await session.execute(
            select(Account.id, Account.name)
            .where(Account.budget_id == budget_id, EMERGENCY_FUND_ACCOUNT)
            .order_by(Account.name, Account.id)
        )
    ).all()
    return [(r.id, r.name) for r in categories], [(r.id, r.name) for r in accounts]


async def _external(session: AsyncSession, budget_id: uuid.UUID) -> FundExternal:
    from igab.guide.repo import GuideRepository

    resolution = resolve(CONCEPT_KEY, await GuideRepository(session).bindings(budget_id))
    return FundExternal(
        declared=resolution.external_declared,
        amount=resolution.external_amount,
        as_of=resolution.external_as_of,
        note=resolution.note,
    )


async def emergency_fund(
    session: AsyncSession,
    budget_id: uuid.UUID,
    budget_service: BudgetService | None = None,
    today: date | None = None,
) -> EmergencyFund:
    """The emergency fund today: what was chosen, what each part holds, and
    the total every surface quotes."""
    today = today or date.today()
    categories, accounts = await _chosen(session, budget_id)
    external = await _external(session, budget_id)

    category_parts: tuple[FundPart, ...] = ()
    if categories:
        this_month = month_start(today)
        series = await _service(session, budget_service).envelope_series(
            budget_id, [cid for cid, _ in categories], [this_month]
        )
        # Per envelope, because the zero floor is per envelope: one $50 over
        # and one $50 under hold $0 and $50, not $0 between them.
        category_parts = tuple(
            FundPart(cid, name, quantize_cents(series[cid].available[0] or ZERO))
            for cid, name in categories
        )
    account_parts: tuple[FundPart, ...] = ()
    if accounts:
        balances = await AccountRepository(session).balances_for([aid for aid, _ in accounts])
        account_parts = tuple(
            FundPart(aid, name, quantize_cents(balances.get(aid, ZERO))) for aid, name in accounts
        )

    parts = category_parts + account_parts
    total = fold_external(_parts_total(parts), external.amount)
    return EmergencyFund(
        categories=category_parts,
        accounts=account_parts,
        external=external,
        total=None if total is None else quantize_cents(total),
        set_up=bool(parts) or external.declared,
    )


async def fund_balance_at(
    session: AsyncSession,
    budget_id: uuid.UUID,
    fund: EmergencyFund,
    months: Sequence[date],
    budget_service: BudgetService | None = None,
) -> list[Decimal]:
    """What the chosen parts held at the end of each month, oldest first.

    The parts are today's choice, read back through history: an envelope
    tagged today draws its whole past. Envelopes read the Budget page's
    Available month by month (`BudgetService.envelope_series`); accounts their
    balance through the month's end. The declared amount is not here — it has
    no history, and the coverage report carries it flat from when it was given.
    A month before an imported budget's recoverable history reads zero.
    """
    if not months:
        return []
    firsts = [month_start(m) for m in months]
    totals = [ZERO for _ in firsts]
    if fund.categories:
        series = await _service(session, budget_service).envelope_series(
            budget_id, [p.id for p in fund.categories], firsts
        )
        for part in fund.categories:
            for i, available in enumerate(series[part.id].available):
                totals[i] += available or ZERO
    if fund.accounts:
        repo = AccountRepository(session)
        ids = [p.id for p in fund.accounts]
        for i, first in enumerate(firsts):
            sums = await repo.balances_for(ids, as_of=month_end(first))
            totals[i] += sum(sums.values(), ZERO)
    return [quantize_cents(t) for t in totals]
