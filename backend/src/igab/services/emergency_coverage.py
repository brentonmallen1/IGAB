"""How long the emergency fund would last, month by month.

The Essentials report answers "what does a lean month cost" and carries the
current coverage as one card's subtitle. This answers the other question —
*am I covered, and is that getting better* — which is a stock measured against
a flow, and neither half belongs on a chart of monthly spending.

**Coverage is the fund divided by a trailing three-month average**, not by the
month's own essentials. A quiet December over a fund that has not moved would
otherwise show coverage jumping and then falling back, which is a story about
December, not about the fund. Three months is the Guide's own window
(`ESSENTIALS_WINDOW_DAYS` is 90) so this line and the roadmap's target cannot
tell different stories about the same household.

**The target moves.** Three months of essentials is not a fixed sum: as
spending grows the target grows with it, and a fund that stood still can lose
coverage without losing a cent. Serving the band per month rather than as one
number is the point of the second chart.

**A self-reported balance has no history.** IGAB cannot know what was in
another bank last March, so an external figure is carried flat from the date
it was reported and not before it, and the response says which months that
touched — a flat line drawn without a word would read as a fund that did not
move. "The date it was reported" is clamped to the newest month the chart
draws: the stamp is always the day the app was told, the chart ends at the
last complete month, so a literal comparison landed the figure one month
beyond its own series and drew $0 under cards reading the real amount.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.domain.dates import add_months, month_start
from igab.domain.money import quantize_cents
from igab.guide.concepts import (
    FULL_EMERGENCY_FUND_MONTHS_HIGH,
    FULL_EMERGENCY_FUND_MONTHS_LOW,
)
from igab.guide.detection import budget_service_from
from igab.repositories.account_repo import AccountRepository
from igab.services.budget_service import BudgetService

#: Months of spending averaged into the denominator. The Guide's essentials
#: window is 90 days; this is that window said in months.
TRAILING_MONTHS = 3


@dataclass
class FundEntities:
    """What counts as the emergency fund, and where its figure comes from."""

    category_ids: list[uuid.UUID]
    account_ids: list[uuid.UUID]
    external_amount: Decimal | None
    external_as_of: date | None
    source: str | None

    @property
    def empty(self) -> bool:
        return not self.category_ids and not self.account_ids and self.external_amount is None


async def fund_entities(session: AsyncSession, budget_id: uuid.UUID) -> FundEntities:
    """The categories and accounts behind `report_basics.emergency_fund`.

    That function returns a total; this returns what it added up, because a
    history needs the parts. Both fold the same resolution, so the newest
    point of the series and the headline balance cannot disagree.
    """
    from igab.guide.bindings import resolve
    from igab.guide.detection import GuideDetection
    from igab.guide.repo import GuideRepository

    rows = await GuideRepository(session).bindings(budget_id)
    resolution = resolve("emergency_fund", rows)

    entities: dict[str, list[uuid.UUID]] = {}
    source: str | None = None
    if resolution.runs_detection:
        finding = await GuideDetection(session).emergency_fund(
            budget_id, resolution.entities or None
        )
        # A finding that found nothing still names no entities; an empty list
        # is the honest answer, not a reason to fall back to guessing again.
        entities = {k: list(v) for k, v in (finding.entities or {}).items()}
        source = finding.reason
    if resolution.external_amount is not None and not source:
        source = "you told us what you have set aside"

    return FundEntities(
        category_ids=entities.get("category", []),
        account_ids=entities.get("account", []),
        external_amount=resolution.external_amount,
        external_as_of=resolution.external_as_of,
        source=source,
    )


def trailing_average(
    totals: list[Decimal], index: int, window: int = TRAILING_MONTHS, *, first_data: int = 0
) -> Decimal:
    """Mean of the `window` months ending at `index`, over what exists.

    Early months have less history behind them, and dividing three months of
    spending by three when only one has happened would halve the denominator
    and double the coverage — a chart that opens on a reassuring number it
    then walks back.

    `first_data` is the index of the first month the budget has any essentials
    history for. Months before it are not months a household spent nothing —
    they are months the budget did not exist — and averaging their zeros in did
    exactly what the paragraph above warns against from the other direction: a
    young budget's chart opened at 6.0 months of runway against a headline of
    2.0, because two thirds of its denominator was a period with no data.
    """
    start = max(first_data, index - window + 1)
    span = totals[start : index + 1]
    return quantize_cents(sum(span, Decimal("0")) / len(span)) if span else Decimal("0")


def coverage_months(balance: Decimal, essentials: Decimal) -> Decimal | None:
    """None, never zero, when there is nothing to divide by.

    A month a household spent nothing essential is a month with no answer, and
    zero coverage is a specific and alarming claim.
    """
    if essentials <= 0:
        return None
    return (balance / essentials).quantize(Decimal("0.1"))


class EmergencyCoverageService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _fund_balance_at(
        self, budgets: "BudgetService", entities: FundEntities, month: date, month_end: date
    ) -> Decimal:
        total = Decimal("0")
        for category_id in entities.category_ids:
            balance = await budgets.get_category_balance(category_id, month)
            # Per category, because the zero floor is per category — two
            # envelopes, one $50 over and one $50 under, hold $0 and $50 and
            # not $0 between them. Same rule as GuideDetection._category_balance.
            total += balance.available
        if entities.account_ids:
            sums = await AccountRepository(self.session).balances_for(
                entities.account_ids, as_of=month_end
            )
            total += sum(sums.values(), Decimal("0"))
        return quantize_cents(total)

    async def coverage(self, budget_id: uuid.UUID, months: int = 12) -> dict:
        from igab.services.report_service import ReportService

        entities = await fund_entities(self.session, budget_id)
        # The budget page's own service, built the way the DI layer builds it,
        # so an envelope's balance here IS the budget page's balance rather
        # than a second derivation pinned equal by a comment.
        budgets = budget_service_from(self.session)

        # The essentials window needs a run-up: the first point's denominator
        # is a three-month average, so it needs the two months before it.
        lead_in = TRAILING_MONTHS - 1
        summary = await ReportService(self.session).essentials_summary(
            budget_id, months=months + lead_in
        )
        series = summary["monthly_series"]
        totals = [row["total"] for row in series]
        # The first month with any essentials history. Everything before it is
        # a month the budget did not exist, not a month nothing was spent.
        first_data = next((i for i, t in enumerate(totals) if t != 0), 0)

        today = date.today()
        first_of_month = month_start(today)
        points = []
        # Nothing identified as the fund: draw no line rather than a flat zero
        # one. A zero series is a claim — "you had nothing all year" — and the
        # honest answer is that the app has not been told what to look at.
        if entities.empty:
            series = []
        # The newest month the chart can draw. The series runs to the last
        # COMPLETE month, so this is in the past — which is the whole reason
        # the external figure needs clamping below.
        newest_end = add_months(series[-1]["month"], 1) - timedelta(days=1) if series else None
        for i, row in enumerate(series):
            if i < lead_in:
                continue
            month: date = row["month"]
            month_end = add_months(month, 1) - timedelta(days=1)
            essentials = trailing_average(totals, i, first_data=first_data)
            balance = await self._fund_balance_at(budgets, entities, month, month_end)
            # A self-reported figure is carried flat from the month it was
            # reported, and "as of now" lands on the newest month the chart
            # draws.
            #
            # `GuideService.set_binding` stamps `as_of` with the day the app
            # was told — deliberately, since the age of the figure is the
            # app's record and not the caller's claim — so through the only
            # write path it is ALWAYS today. The series ends at the last
            # complete month, so comparing the stamp literally put every
            # self-reported fund one month in the future of its own chart:
            # the report drew $0 and 0.0 months beneath cards reading the real
            # amount. Clamping to the newest point is what "as of now" means
            # on a chart of complete months.
            reported = entities.external_as_of
            if reported is None or (newest_end is not None and reported > newest_end):
                reported = newest_end
            external_counted = (
                entities.external_amount is not None
                and reported is not None
                and reported <= month_end
            )
            if external_counted:
                balance = quantize_cents(balance + (entities.external_amount or Decimal("0")))
            points.append(
                {
                    "month": month,
                    "fund_balance": balance,
                    "essentials": essentials,
                    "coverage_months": coverage_months(balance, essentials),
                    "target_low": quantize_cents(essentials * FULL_EMERGENCY_FUND_MONTHS_LOW),
                    "target_high": quantize_cents(essentials * FULL_EMERGENCY_FUND_MONTHS_HIGH),
                    "external_counted": external_counted,
                }
            )

        headline = summary["essentials_90d"]
        balance_now = summary["emergency_fund_balance"]
        return {
            "months": months,
            "tagged": summary["tagged"],
            "fund_balance": balance_now,
            "fund_source": summary["emergency_fund_source"],
            # The Essentials report's own runway, quoted rather than recomputed:
            # one figure, so the two reports cannot disagree about coverage.
            "coverage_months": summary["runway_months"],
            "essentials_monthly": headline,
            "target_low": quantize_cents(headline * FULL_EMERGENCY_FUND_MONTHS_LOW),
            "target_high": quantize_cents(headline * FULL_EMERGENCY_FUND_MONTHS_HIGH),
            "target_range": (FULL_EMERGENCY_FUND_MONTHS_LOW, FULL_EMERGENCY_FUND_MONTHS_HIGH),
            "series": points,
            # A self-reported figure is carried flat from the date it was
            # given. Said out loud, because a flat line drawn without a word
            # reads as a fund that did not move.
            "external_amount": entities.external_amount,
            "external_as_of": entities.external_as_of,
            "current_month": first_of_month,
        }
