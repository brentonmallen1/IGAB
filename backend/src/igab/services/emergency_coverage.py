"""How long the emergency fund would last, month by month.

The Essentials report answers "what does a lean month cost" and carries the
current coverage as one card's subtitle. This answers the other question —
*am I covered, and is that getting better* — which is a stock measured against
a flow, and neither half belongs on a chart of monthly spending.

**Coverage is the fund divided by the essentials figure as of each month** —
`guide.concepts.essentials_at`, the three complete months ending there — not
by the month's own essentials. A quiet December over a fund that has not moved
would otherwise show coverage jumping and then falling back, which is a story
about December, not about the fund. It is the Guide's own figure, read from
the same rows as the headline (`essentials_headline`'s `series`), so the
newest point IS the headline: the headline used to be a rolling ninety days
beside a chart of complete-month averages, and the two disagreed on purpose.

**Sinking-fund bills are spread** when the budget's setting is on, exactly as
the headline spreads them: the rest of a month's essentials takes the
three-month average, and the sinking part is the twelve months ending there
divided by twelve. Charts of what was spent never spread.

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
)
from igab.guide.detection import budget_service_from
from igab.services.emergency_fund import EmergencyFund, fund_balance_at
from igab.services.essentials import LEAD_IN_MONTHS, EssentialMonths, essentials_headline
from igab.services.report_day import reader_today


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

    async def coverage(
        self, budget_id: uuid.UUID, months: int = 12, today: date | None = None
    ) -> dict:
        today = reader_today(today)
        # The budget page's own service, built the way the DI layer builds it,
        # so an envelope's balance here IS the budget page's balance rather
        # than a second derivation pinned equal by a comment.
        budgets = budget_service_from(self.session)

        # The composition the Essentials report quotes, read once for every
        # point: `series` holds `months` answerable complete months after the
        # eleven-month lead-in the twelve-month spread reads, and its newest
        # point is the headline by construction.
        #
        # NOT the Essentials table's `history_window`, deliberately. That one
        # is an average and must not divide by months before the history; this
        # is a series of trailing averages that cut at the history themselves
        # (`history_index`), and whose twelve-month spread reads the months
        # before it as zeros by definition (`spread_average`). Clamping here
        # would shorten the series under the lead-in and drop real points.
        summary = await essentials_headline(self.session, budget_id, today, points=months)
        fund: EmergencyFund = summary["emergency_fund"]
        external = fund.external
        read: EssentialMonths = summary["series"]
        lead_in = LEAD_IN_MONTHS
        # Nothing identified as the fund: draw no line rather than a flat zero
        # one. A zero series is a claim — "you had nothing all year" — and the
        # honest answer is that the app has not been told what to look at.
        drawn = read.months[lead_in:] if fund.draws_history else []

        first_of_month = month_start(today)
        points = []
        # The newest month the chart can draw. The series runs to the last
        # COMPLETE month, so this is in the past — which is the whole reason
        # the external figure needs clamping below.
        newest_end = _month_end(drawn[-1]) if drawn else None
        balances = await fund_balance_at(self.session, budget_id, fund, drawn, budgets)
        for offset, month in enumerate(drawn):
            month_end = _month_end(month)
            essentials = read.at(lead_in + offset).monthly
            balance = balances[offset]
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
            "long_term_essentials": summary["long_term_essentials"],
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
