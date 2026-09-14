"""What a lean month costs — the one wired entry point.

The Guide's essential-expenses signal (and through it the emergency-fund
target, the starter cushion, the checkup and the sizer), the Overview card, the
Essentials report and the Emergency Fund report's headline all read
`essentials_figures`. The arithmetic is `guide.concepts.essentials_monthly`;
the rows are `TransactionRepository.essential_windows`; the budget's
spread-sinking-funds setting is `report_settings`. Nothing else composes the
three, so no surface can quote a figure measured another way.
"""

import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.domain.activity_class import basis_is_chosen
from igab.domain.dates import complete_month_window, month_starts
from igab.domain.money import quantize_cents
from igab.guide.concepts import (
    FULL_EMERGENCY_FUND_MONTHS_HIGH,
    FULL_EMERGENCY_FUND_MONTHS_LOW,
    EssentialsMonthly,
    essentials_monthly,
)
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.emergency_fund import emergency_fund
from igab.services.report_basics import class_excluded_note
from igab.services.report_settings import spread_sinking_funds


async def essentials_figures(
    session: AsyncSession,
    budget_id: uuid.UUID,
    today: date,
    bound: Sequence[uuid.UUID] | None = None,
) -> tuple[EssentialsMonthly, str]:
    """Both essentials figures for `today`, which one the budget reads, and the
    basis that scoped them (`TransactionRepository._necessity_scope`).

    `bound` is the categories the household pointed the Guide's signal at; the
    reports pass none and read the tags.
    """
    windows, basis = await TransactionRepository(session).essential_windows(budget_id, today, bound)
    spread_on = await spread_sinking_funds(session, budget_id)
    return essentials_monthly(windows, spread_on=spread_on), basis


async def reported_essentials(
    session: AsyncSession, budget_id: uuid.UUID, today: date
) -> tuple[EssentialsMonthly, bool]:
    """(both essentials figures, anything tagged?) — what the reports quote.

    The reports read the tags and never the Guide's bound categories. Untagged,
    the figures are zeros: the "all" fallback is burn rate, and a second card
    saying the same number would mislead.
    """
    figures, basis = await essentials_figures(session, budget_id, today)
    if basis_is_chosen(basis):
        return figures, True
    return replace(figures, as_paid=Decimal("0"), spread=Decimal("0")), False


async def essentials_summary(session: AsyncSession, budget_id: uuid.UUID, months: int = 12) -> dict:
    """What a lean month costs, and what a reserve of N months would be.

    The headline (`essentials`) is the Guide's figure — rolling 90 days
    ÷ 3 — so the Overview card, this report and the roadmap's target quote
    one number. The per-category table averages over `months` COMPLETE
    months instead: a partial current month would drag every average
    down. That divergence is deliberate and pinned by test.
    """
    today = date.today()
    txns = TransactionRepository(session)
    # Not clamped to the budget's history, unlike volatility: the table
    # divides by `months` and Emergency Coverage reads it, so clamping is a
    # change to both figures rather than to a window.
    window_start, window_end = complete_month_window(today, months)
    months_list = month_starts(window_start, window_end)

    essentials, tagged = await reported_essentials(session, budget_id, today)
    headline = essentials.monthly
    reserve = [
        {"months": n, "amount": quantize_cents(headline * n)}
        for n in (1, FULL_EMERGENCY_FUND_MONTHS_LOW, FULL_EMERGENCY_FUND_MONTHS_HIGH, 12)
    ]
    # What the household chose to count — read whatever the Guide tracks, so
    # dismissing the Guide's step never blanks the report.
    fund = await emergency_fund(session, budget_id, today=today)
    runway = (
        (fund.total / headline).quantize(Decimal("0.1"))
        if fund.total is not None and headline > 0
        else None
    )
    base = {
        "tagged": tagged,
        "months": months,
        "window_start": window_start,
        "window_end": window_end,
        "essentials": essentials,
        "reserve": reserve,
        "roadmap_range": (FULL_EMERGENCY_FUND_MONTHS_LOW, FULL_EMERGENCY_FUND_MONTHS_HIGH),
        "emergency_fund": fund,
        # The old pair, kept beside the composition until the Counting line
        # replaces what reads them.
        "emergency_fund_balance": fund.total,
        "emergency_fund_source": fund.source,
        "runway_months": runway,
    }
    if not tagged:
        return {
            **base,
            "monthly_total_average": Decimal("0"),
            "categories": [],
            "monthly_series": [
                {"month": m, "total": Decimal("0"), "sinking_total": Decimal("0")}
                for m in months_list
            ],
            # Nothing is tagged, so nothing was pointed at and nothing is
            # missing — but the key is always present, or the client has to
            # know which branch produced its response.
            "class_excluded": [],
        }

    rows, _ = await txns.essential_spend_by_category_month(budget_id, window_start, window_end)
    by_category: dict[str | None, dict] = {}
    # Seeded with every tagged category BEFORE the rows are read, so one
    # that was not spent in this window lands at zero instead of vanishing.
    # Built from rows alone, the list silently became "the tagged
    # categories that happened to have transactions", which sorted by total
    # is indistinguishable from a top-N — the report showed 5 of 8 and
    # looked capped.
    for tagged_cat in await txns.essential_tagged_categories(budget_id):
        by_category[str(tagged_cat.id)] = {
            "category_id": tagged_cat.id,
            "name": tagged_cat.name,
            "group_name": tagged_cat.group_name,
            "total": Decimal("0"),
            "months_with_spend": 0,
        }
    by_month: dict[date, Decimal] = {m: Decimal("0") for m in months_list}
    sinking_by_month: dict[date, Decimal] = dict(by_month)
    for r in rows:
        key = str(r.category_id) if r.category_id else None
        magnitude = -Decimal(r.total)  # spending is stored negative
        entry = by_category.setdefault(
            key,
            {
                "category_id": r.category_id,
                "name": r.category_name or "Uncategorized",
                "group_name": r.group_name,
                "total": Decimal("0"),
                "months_with_spend": 0,
            },
        )
        entry["total"] += magnitude
        entry["months_with_spend"] += 1
        month = r.month.date() if hasattr(r.month, "date") else r.month
        by_month[month] = by_month.get(month, Decimal("0")) + magnitude
        if r.sinking:
            sinking_by_month[month] = sinking_by_month.get(month, Decimal("0")) + magnitude

    # By spend, then by name — so the zero rows sort to the bottom in a
    # readable order rather than in whatever order they were seeded.
    categories = sorted(by_category.values(), key=lambda c: (-c["total"], c["name"]))
    for c in categories:
        c["total"] = quantize_cents(c["total"])
        c["monthly_average"] = quantize_cents(c["total"] / months)
    grand = sum((c["total"] for c in categories), Decimal("0"))
    # What was tagged and still not counted. Tagging a category is pointing
    # at it, which is the condition the note was written for — and the case
    # that misled: a mortgage tagged Essential is now counted, but a
    # category tagged Essential AND Savings still is not, and silence there
    # would be the same bug wearing a different class.
    excluded, _ = await txns.essential_excluded_by_class(budget_id, window_start, window_end)
    return {
        **base,
        "monthly_total_average": quantize_cents(grand / months),
        "categories": categories,
        "monthly_series": [
            {
                "month": m,
                "total": quantize_cents(by_month[m]),
                "sinking_total": quantize_cents(sinking_by_month[m]),
            }
            for m in months_list
        ],
        "class_excluded": class_excluded_note(excluded, scoped=True) or [],
    }
