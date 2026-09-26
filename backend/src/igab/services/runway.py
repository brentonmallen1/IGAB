"""The runway, read for a budget — wiring for `domain.runway`.

The Overview's Runway card and the Cash Projection's "If income stopped" line
both read `runway_read`; the Emergency Fund report and the Essentials report
read the same rule at (Essentials, the fund) through `essentials_headline`.
The monthly figures are the Essentials headline's own composition
(`services.essentials`, `guide.concepts.essentials_at`) applied to each
basis's rows; the money is `services.runway_holdings`.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.domain.activity_class import NecessityTier, basis_is_chosen
from igab.domain.runway import (
    PICKER_MONEY,
    Holdings,
    LinePoint,
    RunwayFigure,
    SpendingBasis,
    burn_down,
    default_basis,
    figure,
)
from igab.services.emergency_fund import emergency_fund
from igab.services.essentials import EssentialMonths, essential_months, spending_months
from igab.services.runway_holdings import holdings


@dataclass(frozen=True)
class SpendingFigures:
    """What a month costs on each basis, as of the last complete month; None
    for a tier nothing is tagged into — unknown, not zero."""

    monthly: dict[SpendingBasis, Decimal | None]
    #: The complete months every basis averages — one window for all three.
    window_start: date | None
    window_end: date | None


def _known(months: EssentialMonths) -> Decimal | None:
    return months.latest.monthly if basis_is_chosen(months.basis) else None


async def spending_figures(
    session: AsyncSession, budget_id: uuid.UUID, today: date
) -> SpendingFigures:
    """The three bases over the Essentials headline's window: all spending,
    the Cost of Living tier and the Essentials tier, each through
    `essentials_at` with the budget's spread setting. The Essentials figure
    is the headline itself (`reported_months` reads the same call)."""
    everything = (await spending_months(session, budget_id, today)).latest
    living = await essential_months(session, budget_id, today, tier=NecessityTier.COST_OF_LIVING)
    lean = await essential_months(session, budget_id, today)
    return SpendingFigures(
        monthly={
            SpendingBasis.ALL: everything.monthly,
            SpendingBasis.COST_OF_LIVING: _known(living),
            SpendingBasis.ESSENTIALS: _known(lean),
        },
        window_start=everything.window_start,
        window_end=everything.window_end,
    )


@dataclass(frozen=True)
class RunwayRead:
    """Every choice the Cash Projection offers, and the Overview's."""

    #: Every spending basis × every picker money, in picker order.
    options: list[RunwayFigure]
    #: The Overview's runway (`domain.runway.default_basis`).
    default: RunwayFigure
    #: Whether an emergency fund with a figure is chosen — without one the
    #: default falls back to the cash, and the card says why.
    fund_chosen: bool
    #: Whether anything is tagged Essential — without it the default falls
    #: back to all spending, and the card says why.
    essentials_known: bool
    window_start: date | None
    window_end: date | None
    holdings: Holdings
    today: date

    def line(self, option: RunwayFigure, end: date) -> list[LinePoint]:
        """`option`'s "If income stopped" line, from today to `end`."""
        return burn_down(option.money_total, option.monthly_spending, self.today, end)


async def runway_read(session: AsyncSession, budget_id: uuid.UUID, today: date) -> RunwayRead:
    """The runway at every choice, as of the reader's `today`."""
    fund = await emergency_fund(session, budget_id, today=today)
    held = await holdings(session, budget_id, today, fund)
    spent = await spending_figures(session, budget_id, today)
    options = [
        figure(spending, money, spent.monthly[spending], held, today)
        for spending in SpendingBasis
        for money in PICKER_MONEY
    ]
    fund_chosen = fund.total is not None
    essentials_known = spent.monthly[SpendingBasis.ESSENTIALS] is not None
    spending, money = default_basis(essentials_known, fund_chosen)
    return RunwayRead(
        options=options,
        default=figure(spending, money, spent.monthly[spending], held, today),
        fund_chosen=fund_chosen,
        essentials_known=essentials_known,
        window_start=spent.window_start,
        window_end=spent.window_end,
        holdings=held,
        today=today,
    )
