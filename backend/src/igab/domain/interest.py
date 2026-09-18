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

Pure: numbers in, a number out.
"""

from decimal import Decimal

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
