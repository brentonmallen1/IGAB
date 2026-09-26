"""What a lean month costs — the one wired entry point.

The Guide's essential-expenses signal (and through it the emergency-fund
target, the starter cushion, the checkup and the sizer), the Overview card, the
Essentials report and the Emergency Fund report — its headline and every point
of its chart — all read `essential_months`. The arithmetic is
`guide.concepts.essentials_at`; the rows are
`TransactionRepository.essential_spend_by_category_month`; the budget's
spread-sinking-funds setting is `report_settings`. Nothing else composes the
three, so no surface can quote a figure measured another way.
"""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.domain.activity_class import NecessityTier, basis_is_chosen
from igab.domain.dates import complete_month_window, history_index, month_starts
from igab.domain.money import quantize_cents
from igab.domain.runway import MoneyBasis, SpendingBasis, figure
from igab.domain.spending import UNCATEGORIZED
from igab.guide.concepts import (
    FULL_EMERGENCY_FUND_MONTHS_HIGH,
    FULL_EMERGENCY_FUND_MONTHS_LOW,
    SPREAD_MONTHS,
    EssentialsMonthly,
    essentials_at,
)
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.emergency_fund import emergency_fund
from igab.services.report_basics import class_excluded_note, history_window
from igab.services.report_day import reader_today
from igab.services.report_settings import spread_sinking_funds
from igab.services.runway_holdings import holdings


@dataclass(frozen=True)
class EssentialMonths:
    """Essential spending per COMPLETE month, oldest first, ending last month
    — everything `essentials_at` needs, read once.

    `points` months are answerable (the newest `points`); the eleven before
    them are the lead-in the twelve-month spread reads. `basis` says how the
    rows were scoped (`TransactionRepository._necessity_scope`).
    """

    months: list[date]
    totals: list[Decimal]
    sinking: list[Decimal]
    first_data: int
    spread_on: bool
    basis: str

    def at(self, index: int) -> EssentialsMonthly:
        return essentials_at(
            self.months,
            self.totals,
            self.sinking,
            index,
            first_data=self.first_data,
            spread_on=self.spread_on,
        )

    @property
    def latest(self) -> EssentialsMonthly:
        """The figure as of the last complete month — the headline."""
        return self.at(len(self.months) - 1)


#: Months before the first answerable one that a figure still reads: the
#: twelve-month spread needs the eleven before it (the three-month average
#: needs only two of them).
LEAD_IN_MONTHS = SPREAD_MONTHS - 1


async def essential_months(
    session: AsyncSession,
    budget_id: uuid.UUID,
    today: date,
    *,
    points: int = 1,
    bound: Sequence[uuid.UUID] | None = None,
    tier: NecessityTier = NecessityTier.ESSENTIAL,
) -> EssentialMonths:
    """The last `points` complete months before the reader's `today`, with
    their lead-in, as `essentials_at` reads them.

    `bound` is the categories the household pointed the Guide's signal at; the
    reports pass none and read the tags. `tier` is which necessity tier's rows
    are read: the lean one unless the runway asks for Cost of living.
    """

    async def rows(repo: TransactionRepository, start: date, end: date) -> tuple[list, str]:
        return await repo.essential_spend_by_category_month(budget_id, start, end, bound, tier=tier)

    return await _months(session, budget_id, today, points, rows)


async def spending_months(
    session: AsyncSession, budget_id: uuid.UUID, today: date
) -> EssentialMonths:
    """ALL spending (`TransactionRepository.spending_by_month`) read exactly
    as the Essentials headline reads its tier — the same complete months, the
    same history cut, the same spread setting — so the runway's three bases
    differ in which rows they count and in nothing else. Basis "all": every
    category, which for spending is the answer, not a fallback."""

    async def rows(repo: TransactionRepository, start: date, end: date) -> tuple[list, str]:
        return await repo.spending_by_month(budget_id, start, end), "all"

    return await _months(session, budget_id, today, 1, rows)


async def _months(
    session: AsyncSession,
    budget_id: uuid.UUID,
    today: date,
    points: int,
    read: Callable[[TransactionRepository, date, date], Awaitable[tuple[list, str]]],
) -> EssentialMonths:
    """The window, the history cut and the spread setting, composed once for
    every monthly figure `essentials_at` reads; `read` supplies the rows."""
    start, end = complete_month_window(today, points + LEAD_IN_MONTHS)
    months = month_starts(start, end)
    repo = TransactionRepository(session)
    rows, basis = await read(repo, start, end)
    series = monthly_series(rows, months)
    return EssentialMonths(
        months=months,
        totals=[row["total"] for row in series],
        sinking=[row["sinking_total"] for row in series],
        first_data=history_index(months, await repo.earliest_date(budget_id)),
        spread_on=await spread_sinking_funds(session, budget_id),
        basis=basis,
    )


async def essentials_figures(
    session: AsyncSession,
    budget_id: uuid.UUID,
    today: date,
    bound: Sequence[uuid.UUID] | None = None,
) -> tuple[EssentialsMonthly, str]:
    """Both essentials figures as of the reader's `today`, and the basis that
    scoped them — what the Guide's signal quotes."""
    months = await essential_months(session, budget_id, today, bound=bound)
    return months.latest, months.basis


async def reported_months(
    session: AsyncSession, budget_id: uuid.UUID, today: date, *, points: int = 1
) -> tuple[EssentialMonths, bool]:
    """`essential_months` as the reports read it — by the tags, never the
    Guide's bound categories — and whether anything is tagged.

    Untagged, every month is zero: the "all" fallback is burn rate, and a
    second card saying the same number would mislead.
    """
    months = await essential_months(session, budget_id, today, points=points)
    if basis_is_chosen(months.basis):
        return months, True
    zeros = [Decimal("0")] * len(months.months)
    return replace(months, totals=zeros, sinking=list(zeros)), False


async def reported_essentials(
    session: AsyncSession, budget_id: uuid.UUID, today: date
) -> tuple[EssentialsMonthly, bool]:
    """(both essentials figures, anything tagged?) — what the reports quote."""
    months, tagged = await reported_months(session, budget_id, today)
    return months.latest, tagged


async def essentials_headline(
    session: AsyncSession, budget_id: uuid.UUID, today: date, *, points: int = 1
) -> dict:
    """The figures no window moves: the Guide's lean month, the reserves it
    implies, the emergency fund and how many lean months it covers.

    Shared by the Essentials report and Emergency Coverage, which quotes this
    `fund_runway` rather than recomputing it — one figure, so the two reports
    cannot disagree about coverage. `today` is the reader's, as the Overview
    card's is. `series` is the months the headline was read from, `points` of
    them answerable, so the Emergency Fund chart draws its points from the same
    read and its newest point's essentials IS the headline.
    """
    months, tagged = await reported_months(session, budget_id, today, points=points)
    essentials = months.latest
    headline = essentials.monthly
    # What the household chose to count — read whatever the Guide tracks, so
    # dismissing the Guide's step never blanks the report.
    fund = await emergency_fund(session, budget_id, today=today)
    tagged_categories = await TransactionRepository(session).essential_tagged_categories(budget_id)
    return {
        "tagged": tagged,
        "essentials": essentials,
        "series": months,
        "tagged_categories": tagged_categories,
        #: How many Essential categories are also Long-term expense. With
        #: none, spreading has nothing to spread: the toggle is hidden and the
        #: page says why rather than offering a switch that changes nothing.
        "long_term_essentials": sum(1 for c in tagged_categories if c.sinking),
        "reserve": [
            {"months": n, "amount": quantize_cents(headline * n)}
            for n in (1, FULL_EMERGENCY_FUND_MONTHS_LOW, FULL_EMERGENCY_FUND_MONTHS_HIGH, 12)
        ],
        "roadmap_range": (FULL_EMERGENCY_FUND_MONTHS_LOW, FULL_EMERGENCY_FUND_MONTHS_HIGH),
        "emergency_fund": fund,
        #: How long the fund lasts on Essentials alone, what the cards owe
        #: taken out — the runway rule (`domain.runway`) at (Essentials, the
        #: fund), and the Emergency Fund report's "Covered". It divided the
        #: fund by Essentials and left the cards out without a word.
        "fund_runway": figure(
            SpendingBasis.ESSENTIALS,
            MoneyBasis.FUND,
            headline if tagged else None,
            await holdings(session, budget_id, today, fund),
            today,
        ),
    }


async def essential_rows(
    session: AsyncSession, budget_id: uuid.UUID, start: date, end: date, *, tagged: bool
) -> list:
    """Tagged essential spending per category per month over [start, end]
    (`TransactionRepository.essential_spend_by_category_month`) — none when
    nothing is tagged: the reports read the tags, and the untagged fallback is
    burn rate under another name."""
    if not tagged:
        return []
    rows, _ = await TransactionRepository(session).essential_spend_by_category_month(
        budget_id, start, end
    )
    return rows


def monthly_series(rows: Sequence, months: Sequence[date]) -> list[dict]:
    """Per month, what `essential_rows` spent as paid and its sinking-fund
    part, positive, every month present — the Essentials chart, and the
    series Emergency Coverage divides its fund by."""
    totals = dict.fromkeys(months, Decimal("0"))
    sinking = dict(totals)
    for r in rows:
        month = r.month.date() if hasattr(r.month, "date") else r.month
        magnitude = -Decimal(r.total)  # spending is stored negative
        totals[month] = totals.get(month, Decimal("0")) + magnitude
        if r.sinking:
            sinking[month] = sinking.get(month, Decimal("0")) + magnitude
    return [
        {
            "month": m,
            "total": quantize_cents(totals[m]),
            "sinking_total": quantize_cents(sinking[m]),
        }
        for m in months
    ]


async def essentials_summary(
    session: AsyncSession, budget_id: uuid.UUID, months: int = 12, today: date | None = None
) -> dict:
    """What a lean month costs, and what a reserve of N months would be.

    The headline (`essentials`) is the Guide's figure — the last three
    complete months (`essentials_at`) — so the Overview card, this report and
    the roadmap's target quote one number. The per-category table averages
    over the `months` complete months the picker chose instead
    (`history_window`), which on the default twelve is a longer view of the
    same kind of month; the two agree when spending is flat.

    The table divides by the months it read, `months_averaged`. It divided by
    `months` — the setting, not the window — and never clamped to the
    history, so "All time" on a budget three complete months old divided
    three months of rent by four.
    """
    today = reader_today(today)
    window_start, window_end = await history_window(session, budget_id, months, today)
    months_list = month_starts(window_start, window_end)
    n = len(months_list)

    head = await essentials_headline(session, budget_id, today)
    rows = await essential_rows(session, budget_id, window_start, window_end, tagged=head["tagged"])
    tagged_categories = head.pop("tagged_categories")
    head.pop("series")
    base = {
        **head,
        "months": months,
        "window_start": window_start,
        "window_end": window_end,
        #: How many complete months the table's averages divide by: `months`,
        #: or fewer when the history is younger than that.
        "months_averaged": n,
        "monthly_series": monthly_series(rows, months_list),
    }
    if not head["tagged"]:
        return {
            **base,
            "monthly_total_average": Decimal("0"),
            "categories": [],
            # Nothing is tagged, so nothing was pointed at and nothing is
            # missing — but the key is always present, or the client has to
            # know which branch produced its response.
            "class_excluded": [],
        }

    txns = TransactionRepository(session)
    by_category: dict[str | None, dict] = {}
    # Seeded with every tagged category BEFORE the rows are read, so one
    # that was not spent in this window lands at zero instead of vanishing.
    # Built from rows alone, the list silently became "the tagged
    # categories that happened to have transactions", which sorted by total
    # is indistinguishable from a top-N — the report showed 5 of 8 and
    # looked capped.
    for tagged_cat in tagged_categories:
        by_category[str(tagged_cat.id)] = {
            "category_id": tagged_cat.id,
            "name": tagged_cat.name,
            "group_name": tagged_cat.group_name,
            "total": Decimal("0"),
            "months_with_spend": 0,
        }
    for r in rows:
        key = str(r.category_id) if r.category_id else None
        entry = by_category.setdefault(
            key,
            {
                "category_id": r.category_id,
                "name": r.category_name or UNCATEGORIZED,
                "group_name": r.group_name,
                "total": Decimal("0"),
                "months_with_spend": 0,
            },
        )
        entry["total"] += -Decimal(r.total)  # spending is stored negative
        entry["months_with_spend"] += 1

    # By spend, then by name — so the zero rows sort to the bottom in a
    # readable order rather than in whatever order they were seeded.
    categories = sorted(by_category.values(), key=lambda c: (-c["total"], c["name"]))
    for c in categories:
        c["total"] = quantize_cents(c["total"])
        c["monthly_average"] = quantize_cents(c["total"] / n) if n else Decimal("0")
    grand = sum((c["total"] for c in categories), Decimal("0"))
    # What was tagged and still not counted. Tagging a category is pointing
    # at it, which is the condition the note was written for — and the case
    # that misled: a mortgage tagged Essential is now counted, but a
    # category tagged Essential AND Savings still is not, and silence there
    # would be the same bug wearing a different class.
    excluded, _ = await txns.essential_excluded_by_class(budget_id, window_start, window_end)
    return {
        **base,
        "monthly_total_average": quantize_cents(grand / n) if n else Decimal("0"),
        "categories": categories,
        "class_excluded": class_excluded_note(excluded, scoped=True) or [],
    }
