"""Income Split: where take-home pay went over a window — the wiring.

The rows are `TransactionRepository.income_split_by_category`; income and
saved are the Savings Rate's own figures (`report_basics.savings_contributors`
over the same window), so the "20" here is the Savings Rate's numerator and
cannot be a second reading of it; the arithmetic is `domain.income_split`.
Nothing else composes the three.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Liability
from igab.domain.activity_class import NecessityTier, basis_is_chosen
from igab.domain.income_split import (
    UNCATEGORIZED,
    CategoryRow,
    IncomeSplit,
    Minimum,
    SavedPart,
    clamp_to_history,
    months_covered,
    partition,
    spread_year,
    strict_reading,
    window_end_for,
)
from igab.domain.money import quantize_cents
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.liability_service import LiabilityService
from igab.services.report_basics import savings_contributors
from igab.services.report_day import reader_today
from igab.services.report_settings import spread_sinking_funds


def _category_rows(rows: list) -> list[CategoryRow]:
    return [
        CategoryRow(
            bucket=r.bucket,
            category_id=r.category_id,
            name=r.category_name,
            group_name=r.group_name,
            is_debt=bool(r.is_debt),
            sinking=bool(r.sinking),
            # Outflows are stored negative; every bucket here is an outflow.
            outflow=-Decimal(r.total),
            count=int(r.count),
            liability_id=r.liability_id,
            counterpart_name=r.counterpart_name,
        )
        for r in rows
    ]


async def _minimums(
    session: AsyncSession, liability_ids: set[uuid.UUID], today: date
) -> dict[uuid.UUID, Minimum]:
    """Each paid debt's minimum as of today (`LiabilityService.minimum_due_now`,
    the figure the Liabilities page shows)."""
    if not liability_ids:
        return {}
    service = LiabilityService(
        LiabilityRepository(session),
        AccountRepository(session),
        CategoryRepository(session),
        TransactionRepository(session),
    )
    liabilities = (
        (await session.execute(select(Liability).where(Liability.id.in_(liability_ids))))
        .scalars()
        .all()
    )
    out: dict[uuid.UUID, Minimum] = {}
    for liability in liabilities:
        status = await service.get_status(liability, today)
        out[liability.id] = Minimum(
            name=liability.name,
            monthly=LiabilityService.minimum_due_now(
                liability, status.current_balance, status.modelled_interest_this_month
            ),
        )
    return out


async def income_split(
    session: AsyncSession,
    budget_id: uuid.UUID,
    start: date,
    end: date,
    today: date | None = None,
) -> dict:
    """The split over [start, end], read through the reader's today and never
    before the month the budget's history starts."""
    today = reader_today(today)
    repo = TransactionRepository(session)
    end = window_end_for(end, today)
    start, clamped = clamp_to_history(start, await repo.earliest_date(budget_id))
    months, whole = months_covered(start, end)
    tagged = basis_is_chosen(await repo.necessity_basis(budget_id, NecessityTier.ESSENTIAL))

    contributors = await savings_contributors(session, budget_id, start, end, today)
    spread_on = await spread_sinking_funds(session, budget_id)
    rows = _category_rows(await repo.income_split_by_category(budget_id, start, end))

    year_sinking: dict[tuple[str, uuid.UUID | None], Decimal] = {}
    if spread_on and any(r.sinking and r.bucket != UNCATEGORIZED for r in rows):
        year_start, year_end = spread_year(end)
        for r in _category_rows(
            await repo.income_split_by_category(budget_id, year_start, year_end)
        ):
            if r.sinking:
                key = (r.bucket, r.category_id)
                year_sinking[key] = year_sinking.get(key, Decimal("0")) + r.outflow

    liability_ids = {r.liability_id for r in rows if r.is_debt and r.liability_id is not None}
    split = partition(
        income=contributors["income"],
        rows=rows,
        saved=[
            SavedPart(name=c["name"], reason_label=c["reason_label"], total=c["total"])
            for c in contributors["savings_contributors"]
        ],
        months=months,
        spread_on=spread_on,
        year_sinking=year_sinking,
        minimums=await _minimums(session, liability_ids, today),
    )
    return _served(split, start, end, today, months, whole, clamped, tagged, spread_on)


def _line(line) -> dict:
    return {
        "category_id": line.category_id,
        "name": line.name,
        "group_name": line.group_name,
        "reason": line.reason,
        "total": line.total,
        "count": line.count,
        "spread": line.spread,
        "as_paid": line.as_paid,
        "minimum": line.minimum,
        "above_minimum": line.above_minimum,
        "minimum_unknown": line.minimum_unknown,
    }


def _served(
    split: IncomeSplit,
    start: date,
    end: date,
    today: date,
    months: Decimal,
    whole: bool,
    clamped: bool,
    tagged: bool,
    spread_on: bool,
) -> dict:
    strict_needs, strict_savings_debt = strict_reading(split)
    return {
        "start_date": start,
        "end_date": end,
        "months": quantize_cents(months),
        "whole_months": whole,
        #: The range runs to today: a month in progress, its income in and its
        #: spending still arriving — so Left over reads high, and the page says so.
        "running": end >= today,
        "clamped": clamped,
        "tagged": tagged,
        "spread_on": spread_on,
        "income": split.income,
        "needs": {"total": split.needs_total, "lines": [_line(x) for x in split.needs]},
        "wants": {
            "total": split.wants_total,
            "committed": [_line(x) for x in split.committed],
            "chosen": [_line(x) for x in split.chosen],
        },
        "savings_debt": {
            "total": split.savings_debt_total,
            "saved": [_line(x) for x in split.saved],
            "debt": [_line(x) for x in split.debt],
        },
        "uncategorized": {"total": split.uncategorized, "count": split.uncategorized_count},
        "left_over": split.left_over,
        "strict": {"needs": strict_needs, "savings_debt": strict_savings_debt},
    }
