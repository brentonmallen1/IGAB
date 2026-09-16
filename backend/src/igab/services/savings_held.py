"""The held part of "saved", read from the budget.

`domain/savings.py` says what held means and why; this module only fetches
the balances it is computed from. Every kept-here Savings envelope
(`category_filters.HOLDS_SAVINGS`) is read through `BudgetService.
envelope_series` — the Budget page's own Available, with its import anchor
and card correction — and cut mid-month by `TransactionRepository.
sum_categories_dated_after`, so held never assembles a balance of its own.

Which envelopes hold is read from their tags *now*: an envelope switched to
kept here counts its whole history as held, the same way a Savings tag added
today reclassifies last year's rows.

**One bound, stated here.** A mid-month cut subtracts the envelope's raw
register rows dated after the cut. For an envelope the card walk corrects (a
card refund that repaid uncovered debt, `_card_corrected`), the page's
activity for such a refund is the refund less what it repaid, so a cut
between that refund's month start and its date reads the balance low by the
repaid part. Month-end cuts subtract nothing and are exact; the gap closes on
the refund's date.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category
from igab.domain.dates import month_end
from igab.domain.savings import balance_at, held_change, held_over, month_cuts, window_cuts
from igab.repositories.category_filters import HOLDS_SAVINGS
from igab.repositories.transaction_repo import TransactionRepository

if TYPE_CHECKING:
    from igab.services.budget_service import BudgetService

ZERO = Decimal("0")


async def kept_envelopes(session: AsyncSession, budget_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """{id: name} of the envelopes whose balance is savings."""
    rows = await session.execute(
        select(Category.id, Category.name).where(Category.budget_id == budget_id, HOLDS_SAVINGS)
    )
    return {r.id: r.name for r in rows.all()}


async def _balances(
    session: AsyncSession,
    budget_id: uuid.UUID,
    envelope_ids: Sequence[uuid.UUID],
    cuts: Sequence[date],
    budget_service: BudgetService | None,
) -> dict[uuid.UUID, list[Decimal | None]]:
    """Each envelope's balance at each cut, None where unrecovered."""
    if not envelope_ids or not cuts:
        return {}
    if budget_service is None:
        # Lazily, as savings_report does: guide.detection imports the report
        # modules' neighbours at import time.
        from igab.guide.detection import budget_service_from

        budget_service = budget_service_from(session)
    months = sorted({c.replace(day=1) for c in cuts})
    series = await budget_service.envelope_series(budget_id, list(envelope_ids), months)
    index = {m: i for i, m in enumerate(months)}
    txns = TransactionRepository(session)
    after: dict[date, dict[uuid.UUID, Decimal]] = {}
    for cut in set(cuts):
        after[cut] = await txns.sum_categories_dated_after(
            budget_id, envelope_ids, cut, month_end(cut)
        )
    return {
        cid: [
            balance_at(
                series[cid].available[index[cut.replace(day=1)]],
                after[cut].get(cid, ZERO),
            )
            for cut in cuts
        ]
        for cid in envelope_ids
    }


async def held_by_envelope(
    session: AsyncSession,
    budget_id: uuid.UUID,
    start: date,
    end: date,
    budget_service: BudgetService | None = None,
) -> dict[uuid.UUID, tuple[str, Decimal]]:
    """{envelope: (name, held)} over [start, end], every kept-here envelope
    present — zeros included, so a caller decides what to omit."""
    envelopes = await kept_envelopes(session, budget_id)
    balances = await _balances(
        session, budget_id, list(envelopes), window_cuts(start, end), budget_service
    )
    return {cid: (name, held_over(balances[cid])) for cid, name in envelopes.items()}


async def held_between(
    session: AsyncSession,
    budget_id: uuid.UUID,
    start: date,
    end: date,
    budget_service: BudgetService | None = None,
) -> Decimal:
    """What every kept-here envelope held over [start, end], together."""
    per = await held_by_envelope(session, budget_id, start, end, budget_service)
    return sum((held for _, held in per.values()), ZERO)


async def held_by_month(
    session: AsyncSession,
    budget_id: uuid.UUID,
    months: Sequence[date],
    today: date,
    budget_service: BudgetService | None = None,
) -> list[Decimal]:
    """Held per month, aligned with `months` (consecutive month starts), the
    running month read through today. Adds up to `held_between(months[0],
    today)`: the cuts are that window's (`month_cuts`)."""
    cuts = month_cuts(months, today)
    envelopes = await kept_envelopes(session, budget_id)
    balances = await _balances(session, budget_id, list(envelopes), cuts, budget_service)
    return [
        sum((held_change(b[i], b[i + 1]) for b in balances.values()), ZERO)
        for i in range(len(months))
    ]
