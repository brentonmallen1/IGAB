"""The basic reports: spending over time for a chosen scope, income by
source, and what the essentials reserve is measured against.

Split from report_service.py, which is over the file-length budget and may
only shrink. These read the same predicates it does — `spending_trends`
goes through `ReportService._spending_query` so a line here and a bar there
cannot total differently — and nothing here decides money the budget page
does not already show.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Payee, Transaction
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    SPENDING_CLASSES,
    ActivityClass,
    apply_class_joins,
)
from igab.domain.dates import add_months
from igab.domain.money import quantize_cents
from igab.repositories.txn_filters import (
    CASH_FLOW_ROW,
    LEAF,
    NOT_DELETED,
    ON_BUDGET_ACCOUNT,
    POSTED,
)

if TYPE_CHECKING:
    from igab.services.report_service import ReportService


def _months_in_range(start_date: date, end_date: date) -> list[date]:
    months = []
    cur = start_date.replace(day=1)
    while cur <= end_date:
        months.append(cur)
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


def _subtract_months(d: date, months: int) -> date:
    """The start of the month `months` before `d`'s.

    Discarding the day is deliberate — every caller here is keying a month
    bucket. `add_months` is the one that preserves it.
    """
    # `replace(day=1)` rather than domain.dates.month_start: `month_start` is
    # a loop variable throughout this module and importing the name shadows it.
    return add_months(d.replace(day=1), -months)


async def spending_trends(
    svc: ReportService,
    budget_id: uuid.UUID,
    start_date: date,
    end_date: date,
    category_ids: list[uuid.UUID] | None = None,
    account_ids: list[uuid.UUID] | None = None,
    include_classes: Sequence[ActivityClass] | None = None,
) -> dict:
    """Spending per category per month over the window.

    `category_ids` is the resolved scope — explicit picks, a saved
    filter's effective set, a tag's members — already merged by the
    route. Months with nothing spent are zero, never missing, so every
    series is the same length as `months`.
    """
    months = _months_in_range(start_date.replace(day=1), end_date)
    index = {m: i for i, m in enumerate(months)}
    q = svc._spending_query(budget_id, start_date, end_date, category_ids, account_ids)
    rows = (await svc.session.execute(q)).all()
    included = {c.value for c in (include_classes or SPENDING_CLASSES)}
    counted = [r for r in rows if r.cls in included]
    other_class = [r for r in rows if r.cls not in included]

    series: dict[uuid.UUID, dict] = {}
    for r in counted:
        entry = series.setdefault(
            r.id,
            {
                "id": r.id,
                "name": r.name,
                "group_id": r.group_id,
                "group_name": r.group_name,
                "monthly": [Decimal("0")] * len(months),
                "total": Decimal("0"),
            },
        )
        magnitude = abs(r.amount)
        entry["monthly"][index[r.date.replace(day=1)]] += magnitude
        entry["total"] += magnitude
    ordered = sorted(series.values(), key=lambda e: e["total"], reverse=True)
    for e in ordered:
        e["monthly"] = [quantize_cents(v) for v in e["monthly"]]
        e["total"] = quantize_cents(e["total"])
    monthly_totals = [
        quantize_cents(sum((e["monthly"][i] for e in ordered), Decimal("0")))
        for i in range(len(months))
    ]
    return {
        "months": months,
        "series": ordered,
        "monthly_totals": monthly_totals,
        "total": quantize_cents(sum(monthly_totals, Decimal("0"))),
        "class_excluded": svc._class_excluded_note(other_class, scoped=bool(category_ids)) or [],
    }


async def income_by_source(session: AsyncSession, budget_id: uuid.UUID, months: int = 12) -> dict:
    """Income per payee per month: on-budget inflows the classifier reads
    as income. Transfers, refunds into envelopes and investment returns
    are other classes and stay out — the same partition every cash-flow
    report uses."""
    today = date.today()
    start_date = _subtract_months(today, months - 1).replace(day=1)
    month_list = _months_in_range(start_date, today)
    index = {m: i for i, m in enumerate(month_list)}
    q = (
        select(
            Transaction.payee_id,
            Payee.name.label("payee_name"),
            Transaction.date,
            Transaction.amount,
            ACTIVITY_CLASS.label("cls"),
        )
        .outerjoin(Payee, Payee.id == Transaction.payee_id)
        .where(
            Transaction.budget_id == budget_id,
            NOT_DELETED,
            POSTED,
            Transaction.amount > 0,
            Transaction.date >= start_date,
            Transaction.date <= today,
            LEAF,
            CASH_FLOW_ROW,
            ON_BUDGET_ACCOUNT,
        )
    )
    rows = (await session.execute(apply_class_joins(q))).all()
    sources: dict[str, dict] = {}
    for r in rows:
        if r.cls != ActivityClass.INCOME.value:
            continue
        key = str(r.payee_id) if r.payee_id else "__none__"
        entry = sources.setdefault(
            key,
            {
                "payee_id": r.payee_id,
                "payee_name": r.payee_name or "No payee",
                "monthly": [Decimal("0")] * len(month_list),
                "total": Decimal("0"),
                "count": 0,
            },
        )
        entry["monthly"][index[r.date.replace(day=1)]] += r.amount
        entry["total"] += r.amount
        entry["count"] += 1
    ordered = sorted(sources.values(), key=lambda e: e["total"], reverse=True)
    for e in ordered:
        e["monthly"] = [quantize_cents(v) for v in e["monthly"]]
        e["total"] = quantize_cents(e["total"])
    monthly_totals = [
        quantize_cents(sum((e["monthly"][i] for e in ordered), Decimal("0")))
        for i in range(len(month_list))
    ]
    return {
        "months": month_list,
        "sources": ordered,
        "monthly_totals": monthly_totals,
        "total": quantize_cents(sum(monthly_totals, Decimal("0"))),
    }


async def emergency_fund(
    session: AsyncSession, budget_id: uuid.UUID
) -> tuple[Decimal | None, str | None]:
    """What the Guide reads as the emergency fund, and why — the bound
    category or account if the person pointed at one, else the Guide's
    own detection. One reader (GuideDetection.emergency_fund), so the
    Essentials report and the roadmap quote the same balance."""
    from igab.guide.bindings import resolve
    from igab.guide.detection import GuideDetection
    from igab.guide.repo import GuideRepository

    rows = await GuideRepository(session).bindings(budget_id)
    resolution = resolve("emergency_fund", rows)
    if not resolution.runs_detection:
        return None, None
    finding = await GuideDetection(session).emergency_fund(budget_id, resolution.entities or None)
    if finding.value is None:
        return None, None
    return quantize_cents(finding.value), finding.reason
