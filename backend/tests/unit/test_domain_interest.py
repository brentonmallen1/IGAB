"""One rate conversion, shared by the schedule and the liability page.

This was written eight times before it had a home: six in the amortization
service as `annual_rate / 100 / 12`, twice in the liabilities API as
`balance * rate / 1200`.
"""

from decimal import Decimal

from igab.domain.interest import monthly_interest, monthly_rate


def test_monthly_rate_is_the_annual_percentage_over_twelve():
    assert monthly_rate(Decimal("6")) == Decimal("6") / Decimal("100") / Decimal("12")


def test_monthly_rate_is_not_quantized():
    """Load-bearing: a schedule multiplies this by a falling balance for up to
    360 months and rounds each month. Rounding the rate first would compound
    a rounding error across the life of a mortgage."""
    rate = monthly_rate(Decimal("6.5"))
    assert rate != rate.quantize(Decimal("0.01"))


def test_monthly_interest_is_cents():
    """6% a year on 2,690 is 13.45 a month."""
    assert monthly_interest(Decimal("2690.00"), Decimal("6")) == Decimal("13.45")


def test_monthly_interest_is_the_one_rule_the_schedule_and_the_api_share():
    """The schedule's `quantize_cents(balance * monthly_rate)` and the API's
    old `quantize_cents(balance * rate / 1200)` were two spellings of this.
    Both now route here, so they cannot round a month differently."""
    balance, annual = Decimal("248900.00"), Decimal("6.125")
    from igab.domain.money import quantize_cents

    assert monthly_interest(balance, annual) == quantize_cents(balance * monthly_rate(annual))
    assert monthly_interest(balance, annual) == quantize_cents(balance * annual / Decimal("1200"))


def test_a_zero_rate_costs_nothing():
    assert monthly_interest(Decimal("2690.00"), Decimal("0")) == Decimal("0.00")
