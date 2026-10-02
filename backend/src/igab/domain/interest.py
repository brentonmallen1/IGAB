"""Turning an annual rate into what one month actually costs.

A loan carries one number the user typed — an annual percentage — and every
figure the app shows about that loan is derived from it: the amortization
schedule's interest column, the debt cascade's per-debt rates, a card's
"1% plus this month's interest" minimum, and the liability page's "this
month's interest is about X".

That conversion was written **eight** times before it lived here: six in
`services/amortization.py` as `annual_rate / 100 / 12`, twice in
`api/v1/liabilities.py` as `balance * rate / 1200`. They agreed, which is
luck rather than design — the two spellings round differently the moment
anyone changes one, and the API's spelling quantizes the product while the
schedule's kept the rate unrounded and quantized later.

Both spellings survive here as two functions, because both are genuinely
needed: a schedule steps month by month and wants the **unrounded rate** so
rounding happens once per month rather than compounding a rounded rate; a
display wants the **cents** for one month at one balance.

A third question lives here too: what THIS month is charged. A lender
charges the balance the month opened with — last month's close — at the rate
in force for the month, which is nothing while a 0% promo still covers it.
`chargeable_rate` and `interest_for_month` answer that, and every reader of
"this month's interest" (the liability page's estimate, the payoff copy, the
"plus interest" minimum) goes through them, so none of them can charge the
post-payment balance or the promo month again.

Pure: numbers in, a number out.
"""

from datetime import date
from decimal import Decimal

from igab.domain.dates import month_end
from igab.domain.money import quantize_cents

ZERO = Decimal("0")

#: Percent to fraction, year to month. Written once.
_PERCENT = Decimal("100")
_MONTHS_PER_YEAR = Decimal("12")


def monthly_rate(annual_rate: Decimal) -> Decimal:
    """The annual percentage as an unrounded monthly fraction.

    6.5 (percent a year) becomes 0.00541666... a month. Deliberately NOT
    quantized: a schedule multiplies this by a falling balance every month and
    rounds each month's interest, so rounding the rate first would compound a
    rounding error across 360 months of a mortgage.
    """
    return annual_rate / _PERCENT / _MONTHS_PER_YEAR


def monthly_interest(balance: Decimal, annual_rate: Decimal) -> Decimal:
    """One month's interest on `balance`, in cents.

    The figure a statement would show and the figure the liability page
    quotes. `balance` is the POSITIVE amount owed — callers that hold a
    liability ledger (negative) negate before calling, so a negative return
    here means someone passed a ledger figure by mistake rather than meaning
    the loan earns interest.
    """
    return quantize_cents(balance * monthly_rate(annual_rate))


def chargeable_rate(
    annual_rate: Decimal | None, promo_end_date: date | None, month: date
) -> Decimal | None:
    """The annual rate `month` is charged at, or None when there is no rate.

    A promo is "0% until X": the stored rate applies only AFTER
    `promo_end_date` (the column says so on the model). A month the promo
    covers to its last day is charged nothing — ZERO, not None, because the
    terms are known and say the month is free.

    A month the promo ends partway through is charged in full. That is the
    conservative reading, and the same direction the live projection takes
    by staying at the contract rate: an estimate that is a few days of
    interest high is reconciled down; one that is low reads a balance as
    smaller than it is. Proration is not modelled.

    `month` may be any day of the month it names.
    """
    if annual_rate is None:
        return None
    if promo_end_date is not None and promo_end_date >= month_end(month):
        return ZERO
    return annual_rate


def interest_for_month(owed_at_open: Decimal, annual_rate: Decimal) -> Decimal:
    """What a month costs: the amount owed as it OPENED, at `annual_rate`.

    `owed_at_open` is last month's closing balance as a positive amount owed
    — never today's balance, which already has this month's payment taken
    off it and so reads every paid month's interest low (24,000 at 6% is
    120.00, not the 117.50 a 500 payment would leave). Zero or less means
    nothing was owed when the month began — paid off, or in credit — and
    costs nothing: a lender does not pay interest on an overpayment.

    `annual_rate` is the CHARGEABLE rate (`chargeable_rate`), so a promo
    month passes zero here rather than being special-cased twice.
    """
    if owed_at_open <= ZERO:
        return quantize_cents(ZERO)
    return monthly_interest(owed_at_open, annual_rate)
