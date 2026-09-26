"""Runway: how long the money lasts if income stopped — the one rule.

"How long does my money last" used to have four answers on four pages, and
none of them said which question it was answering:

- the Overview's "Days Until Zero" divided the budget's cash by the last
  thirty days' burn — every kind of spending, checking alone, card debt and
  savings ignored — and read 17 days on a budget whose checking had not
  dipped below a month's pay in a year;
- the Burn Rate is a speed, not a duration;
- the Cash Projection assumes income carries on;
- the Emergency Fund's "Covered" divided the fund by Essentials and left the
  cards out without saying so.

One rule answers now, and states its two choices wherever it is quoted:

- **What a month costs** (`SpendingBasis`): all spending, Cost of living, or
  Essentials — each the three-complete-month figure the Essentials headline
  reads (`guide.concepts.essentials_at`), so the three differ in membership
  and never in window.
- **What money counts** (`MoneyBasis`): the budget's cash, plus the emergency
  fund, plus all savings — or, on the Emergency Fund report, the fund alone.

**Card debt is always subtracted.** What is owed on an on-budget card is paid
from the same cash the runway spends; a household that stops earning still
owes it. A figure that left it out read the whole card balance as months of
runway.

**Each dollar counts once.** Envelope money — an Emergency fund or Savings
envelope included — is already inside the budget's cash, so "+ emergency
fund" adds what the fund holds OUTSIDE the budget (its marked off-budget
accounts and any amount declared as kept elsewhere) and "+ all savings" adds
every off-budget savings account (the Savings report's accounts) and that same
declared amount. Adding the Savings report's whole Saved total to the cash
would count every savings envelope twice.

Pure: no session, no clock. `today` is the reader's day.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import NamedTuple

from igab.domain.money import quantize_cents

ZERO = Decimal("0")
TENTH = Decimal("0.1")

#: An average calendar month in days (365.25 / 12), so twelve months of
#: runway is a year to the day. The runs-out date and the burn-down line both
#: convert with it, so the line reaches zero on the date the card states.
DAYS_PER_MONTH = Decimal("30.4375")


class SpendingBasis(StrEnum):
    """What a month costs."""

    #: Everything spent — the one spending definition (`txn_filters.SPENDING_ROW`).
    ALL = "all"
    #: The Cost of Living report's wide tier: Essential and Cost of living
    #: categories, plus debt payments by class.
    COST_OF_LIVING = "cost_of_living"
    #: The Essentials headline: categories tagged Essential.
    ESSENTIALS = "essentials"


class MoneyBasis(StrEnum):
    """What money the runway spends."""

    #: The budget's cash — every on-budget account that is not a card, the
    #: balance term of Ready to Assign (`sum_on_budget_balance`).
    CHECKING = "checking"
    #: The cash plus what the emergency fund holds outside the budget.
    WITH_FUND = "with_fund"
    #: The cash plus every off-budget savings account and the fund's declared
    #: outside money.
    WITH_SAVINGS = "with_savings"
    #: The emergency fund alone: the Emergency Fund report's "Covered".
    FUND = "fund"


#: The money a person picks between on the Cash Projection, in picker order.
#: FUND is not one of them: it answers the Emergency Fund report's question,
#: not "how long does my money last".
PICKER_MONEY: tuple[MoneyBasis, ...] = (
    MoneyBasis.CHECKING,
    MoneyBasis.WITH_FUND,
    MoneyBasis.WITH_SAVINGS,
)

#: The Overview's runway: what a lean month costs, against the cash and the
#: fund — the question an emergency fund exists to answer.
DEFAULT_SPENDING = SpendingBasis.ESSENTIALS
DEFAULT_MONEY = MoneyBasis.WITH_FUND


@dataclass(frozen=True)
class Holdings:
    """The money a runway can count, each dollar in exactly one field."""

    #: On-budget cash (`sum_on_budget_balance`): envelopes included.
    cash: Decimal
    #: Owed on on-budget cards, positive (`card_debt`).
    card_debt: Decimal
    #: The emergency fund's total (`services.emergency_fund`): envelopes,
    #: marked accounts and the declared amount. None when nothing is chosen.
    fund: Decimal | None
    #: The fund's marked off-budget accounts — outside the cash.
    fund_accounts: Decimal
    #: The amount declared as kept outside IGAB — outside everything.
    declared: Decimal
    #: Every off-budget savings account (the Savings report's accounts, the
    #: fund's marked accounts among them).
    savings_accounts: Decimal


def card_debt(balances: Iterable[Decimal]) -> Decimal:
    """What is owed across the cards, from their balances (owed is negative,
    `AccountRepository.card_balances`). A card in credit owes nothing and
    lends nothing: its credit is not cash the runway can spend, and netting it
    would let one card's overpayment hide another's debt."""
    return quantize_cents(sum((max(ZERO, -b) for b in balances), ZERO))


def money_for(basis: MoneyBasis, h: Holdings) -> Decimal | None:
    """The money `basis` counts, net of card debt. None when it counts an
    emergency fund nobody has chosen: that is an unanswered question, not a
    fund of zero."""
    if basis is MoneyBasis.CHECKING:
        held = h.cash
    elif basis is MoneyBasis.WITH_FUND:
        if h.fund is None:
            return None
        held = h.cash + h.fund_accounts + h.declared
    elif basis is MoneyBasis.WITH_SAVINGS:
        held = h.cash + h.savings_accounts + h.declared
    else:
        if h.fund is None:
            return None
        held = h.fund
    return quantize_cents(held - h.card_debt)


class Runway(NamedTuple):
    #: Months the money lasts, to one decimal. None when nothing is being
    #: spent (there is no pace to run out at); 0 when the money is already
    #: gone.
    months: Decimal | None
    #: The reader's today plus `months`. None with `months`, and past the
    #: calendar's end.
    runs_out_on: date | None


def _days(months: Decimal) -> int:
    return int((months * DAYS_PER_MONTH).to_integral_value(rounding=ROUND_HALF_UP))


def _later(today: date, days: int) -> date | None:
    try:
        return today + timedelta(days=days)
    except OverflowError:
        return None


def runway(money: Decimal | None, monthly: Decimal | None, today: date) -> Runway:
    """How long `money` lasts at `monthly` a month, from `today`.

    - Nothing known or nothing spent (`monthly` None, zero, or a month whose
      refunds beat its spending): no runway — None, never a large number.
    - Money unknown (a fund nobody chose): None.
    - Money at or below zero — card debt larger than the cash included: 0,
      running out today. The old card hid itself here, at exactly the moment
      its answer mattered most.
    - Otherwise money ÷ monthly, to one decimal; the date from the unrounded
      figure, so 2.96 months and 3.04 months do not share a date.
    """
    if money is None or monthly is None or monthly <= 0:
        return Runway(None, None)
    if money <= 0:
        return Runway(Decimal("0.0"), today)
    exact = money / monthly
    return Runway(exact.quantize(TENTH), _later(today, _days(exact)))


@dataclass(frozen=True)
class RunwayFigure:
    """The rule's answer at one choice, with the choice and its inputs — what
    every surface quotes, so each can say what it read."""

    spending: SpendingBasis
    money: MoneyBasis
    #: What a month costs on `spending`; None when unknown (nothing tagged).
    monthly_spending: Decimal | None
    #: The money `money` counts, card debt already subtracted; None when it
    #: counts a fund nobody has chosen.
    money_total: Decimal | None
    #: What was subtracted for the cards.
    card_debt: Decimal
    months: Decimal | None
    runs_out_on: date | None


def figure(
    spending: SpendingBasis,
    money: MoneyBasis,
    monthly: Decimal | None,
    holdings: Holdings,
    today: date,
) -> RunwayFigure:
    """`runway` at one choice of spending and money."""
    total = money_for(money, holdings)
    months, runs_out_on = runway(total, monthly, today)
    return RunwayFigure(
        spending=spending,
        money=money,
        monthly_spending=monthly,
        money_total=total,
        card_debt=holdings.card_debt,
        months=months,
        runs_out_on=runs_out_on,
    )


class LinePoint(NamedTuple):
    day: date
    balance: Decimal


def burn_down(
    money: Decimal | None, monthly: Decimal | None, start: date, end: date
) -> list[LinePoint]:
    """The "If income stopped" line on the Cash Projection: a straight line
    from `money` on `start`, falling `monthly` a month, drawn to the day it
    reaches zero or to `end`, whichever comes first.

    Two points (one when there is nothing to draw across): the chart joins
    them, so the line is straight by construction rather than by a per-day
    series that could drift from the runway it illustrates. Nothing spent is a
    flat line; money already at or below zero is its starting point alone.
    """
    if money is None:
        return []
    first = LinePoint(start, quantize_cents(money))
    if money <= 0:
        return [first]
    if monthly is None or monthly <= 0:
        return [first, LinePoint(end, quantize_cents(money))]
    out = runway(money, monthly, start).runs_out_on
    if out is not None and out <= end:
        return [first, LinePoint(out, ZERO.quantize(Decimal("0.01")))]
    elapsed = Decimal((end - start).days) / DAYS_PER_MONTH
    return [first, LinePoint(end, quantize_cents(money - monthly * elapsed))]


def default_basis(essentials_known: bool, fund_chosen: bool) -> tuple[SpendingBasis, MoneyBasis]:
    """The Overview's runway, and what it falls back to: Essentials against
    the cash and the fund; all spending when nothing is tagged Essential (an
    untagged Essentials figure is unknown, not zero); the cash alone when no
    fund is chosen. The card states whichever it read."""
    spending = DEFAULT_SPENDING if essentials_known else SpendingBasis.ALL
    money = DEFAULT_MONEY if fund_chosen else MoneyBasis.CHECKING
    return spending, money
