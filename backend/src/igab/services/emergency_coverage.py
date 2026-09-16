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

**Sinking-fund bills are spread** when the budget's setting is on, exactly as
the headline spreads them (`guide.concepts.spread_average`): the rest of a
month's essentials takes the trailing three-month average, and the sinking
part is the twelve months ending there divided by twelve. Off, every point is
the plain trailing average. Charts of what was spent never spread.

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
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.domain.dates import month_end as _month_end
from igab.domain.dates import month_start
from igab.domain.money import quantize_cents
from igab.guide.concepts import (
    FULL_EMERGENCY_FUND_MONTHS_HIGH,
    FULL_EMERGENCY_FUND_MONTHS_LOW,
    SPREAD_MONTHS,
    spread_average,
    trailing_average,
)
from igab.guide.detection import budget_service_from
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.emergency_fund import EmergencyFund, fund_balance_at
from igab.services.essentials import essentials_summary


def history_index(months: list[date], history_from: date | None) -> int:
    """The index of the first month in `months` the budget has history for.

    From the budget's first transaction — `earliest_date`, the start "All
    time" counts from — not from the first month with essentials spending.
    That was the first version, and it is a second answer to "when does this
    budget begin": a real month in which nothing essential was spent read as a
    month before the budget existed, so a household whose first Essential bill
    landed in March had March averaged alone instead of with the two quiet
    months before it.

    A budget with no transactions has no history to cut from: 0.
    """
    if history_from is None:
        return 0
    start = month_start(history_from)
    return next((i for i, m in enumerate(months) if m >= start), len(months))


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

    async def coverage(self, budget_id: uuid.UUID, months: int = 12) -> dict:
        # The budget page's own service, built the way the DI layer builds it,
        # so an envelope's balance here IS the budget page's balance rather
        # than a second derivation pinned equal by a comment.
        budgets = budget_service_from(self.session)

        # The essentials window needs a run-up: the first point's denominator
        # spreads sinking-fund bills over twelve months, so it needs the eleven
        # months before it (the three-month average needs only two of them).
        lead_in = SPREAD_MONTHS - 1
        summary = await essentials_summary(self.session, budget_id, months=months + lead_in)
        # The composition the Essentials report quotes — one reading, so the
        # newest point, the headline and every other surface share a total.
        fund: EmergencyFund = summary["emergency_fund"]
        external = fund.external
        spread_on = summary["essentials"].spread_on
        series = summary["monthly_series"]
        totals = [row["total"] for row in series]
        sinking = [row["sinking_total"] for row in series]
        first_data = history_index(
            [row["month"] for row in series],
            await TransactionRepository(self.session).earliest_date(budget_id),
        )

        today = date.today()
        first_of_month = month_start(today)
        points = []
        # Nothing identified as the fund: draw no line rather than a flat zero
        # one. A zero series is a claim — "you had nothing all year" — and the
        # honest answer is that the app has not been told what to look at.
        if not fund.draws_history:
            series = []
        # The newest month the chart can draw. The series runs to the last
        # COMPLETE month, so this is in the past — which is the whole reason
        # the external figure needs clamping below.
        newest_end = _month_end(series[-1]["month"]) if series else None
        balances = await fund_balance_at(
            self.session,
            budget_id,
            fund,
            [row["month"] for row in series[lead_in:]],
            budgets,
        )
        for i, row in enumerate(series):
            if i < lead_in:
                continue
            month: date = row["month"]
            month_end = _month_end(month)
            essentials = (
                spread_average(totals, sinking, i, first_data=first_data)
                if spread_on
                else trailing_average(totals, i, first_data=first_data)
            )
            balance = balances[i - lead_in]
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
            reported = external.as_of
            if reported is None or (newest_end is not None and reported > newest_end):
                reported = newest_end
            external_counted = (
                external.amount is not None and reported is not None and reported <= month_end
            )
            if external_counted:
                balance = quantize_cents(balance + (external.amount or Decimal("0")))
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

        headline = summary["essentials"].monthly
        return {
            "months": months,
            "tagged": summary["tagged"],
            "fund": fund,
            # The Essentials report's own runway, quoted rather than recomputed:
            # one figure, so the two reports cannot disagree about coverage.
            "coverage_months": summary["runway_months"],
            "essentials": summary["essentials"],
            "target_low": quantize_cents(headline * FULL_EMERGENCY_FUND_MONTHS_LOW),
            "target_high": quantize_cents(headline * FULL_EMERGENCY_FUND_MONTHS_HIGH),
            "target_range": (FULL_EMERGENCY_FUND_MONTHS_LOW, FULL_EMERGENCY_FUND_MONTHS_HIGH),
            "series": points,
            # A self-reported figure is carried flat from the date it was
            # given. Said out loud, because a flat line drawn without a word
            # reads as a fund that did not move.
            "external_amount": external.amount,
            "external_as_of": external.as_of,
            "current_month": first_of_month,
        }
