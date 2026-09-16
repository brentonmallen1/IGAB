"""Spreading sinking-fund bills over twelve months: the pure arithmetic.

`guide.concepts.essentials_monthly` is the headline every surface quotes and
`spread_average` is its month-shaped twin for the coverage series. Figures are
round enough to check on paper: $2,000 a month of ordinary essentials and a
$2,400 yearly premium filed to a Long-term expense category.
"""

from decimal import Decimal as D

from igab.guide.concepts import (
    EssentialsMonthly,
    EssentialsWindows,
    essentials_monthly,
    spread_average,
    trailing_average,
)

#: Three months of $2,000 ordinary essentials, signed as the ledger stores them.
ORDINARY_90D = D("-6000.00")
PREMIUM = D("-2400.00")


def test_no_sinking_funds_spread_equals_as_paid():
    """With no sinking-fund rows the two figures agree to the cent — including
    on a total that does not divide by three evenly."""
    for recent in (D("0"), ORDINARY_90D, D("-1000.00"), D("-0.01")):
        m = essentials_monthly(EssentialsWindows(recent, D("0"), D("0")), spread_on=True)
        assert m.spread == m.as_paid
        assert m.monthly == m.as_paid
    assert essentials_monthly(
        EssentialsWindows(D("-1000.00"), D("0"), D("0")), spread_on=True
    ).as_paid == D("333.33")


def test_an_annual_bill_is_a_twelfth_inside_or_outside_90_days():
    """Paid last week the premium is inside the 90 days: as paid reads
    (6,000 + 2,400) / 3 = 2,800, spread 2,000 + 200 = 2,200. Paid eight months
    ago it is outside: as paid 2,000, spread still 2,200."""
    inside = essentials_monthly(
        EssentialsWindows(ORDINARY_90D + PREMIUM, PREMIUM, PREMIUM), spread_on=True
    )
    assert (inside.as_paid, inside.spread) == (D("2800.00"), D("2200.00"))

    outside = essentials_monthly(EssentialsWindows(ORDINARY_90D, D("0"), PREMIUM), spread_on=True)
    assert (outside.as_paid, outside.spread) == (D("2000.00"), D("2200.00"))


def test_monthly_follows_the_setting():
    windows = EssentialsWindows(ORDINARY_90D + PREMIUM, PREMIUM, PREMIUM)
    assert essentials_monthly(windows, spread_on=True).monthly == D("2200.00")
    assert essentials_monthly(windows, spread_on=False).monthly == D("2800.00")
    # Both figures are served either way; only the choice moves.
    off = essentials_monthly(windows, spread_on=False)
    assert off == EssentialsMonthly(D("2800.00"), D("2200.00"), spread_on=False)


def test_a_refund_to_a_sinking_fund_lowers_the_spread_part():
    """Signed sums: a $400 partial refund of the premium is $400 less spread,
    a twelfth of it a month."""
    windows = EssentialsWindows(ORDINARY_90D, D("0"), PREMIUM + D("400.00"))
    assert essentials_monthly(windows, spread_on=True).spread == D("2166.67")


def _months(values):
    return [D(v) for v in values]


def test_the_spread_part_is_not_cut_at_history():
    """A budget whose history starts at index 11 and paid the premium that
    month: the ordinary part averages the one month that exists, the premium
    is still divided by twelve. Cutting it at the history would read the whole
    premium as that month's bill."""
    totals = _months(["0"] * 11 + ["4400"])
    sinking = _months(["0"] * 11 + ["2400"])
    assert spread_average(totals, sinking, 11, first_data=11) == D("2200.00")


def test_spread_average_with_no_sinking_is_the_trailing_average():
    totals = _months(["300", "600", "900", "1200"])
    zeros = _months(["0"] * 4)
    for i in range(4):
        for first in (0, 2):
            assert spread_average(totals, zeros, i, first_data=first) == trailing_average(
                totals, i, first_data=first
            )


def test_spread_average_sums_the_twelve_months_ending_at_the_index():
    """Index 13 of a series with the premium at index 1: months 2..13 do not
    include it, so it has left the spread. At index 12 it is still in."""
    totals = _months(["2000", "4400"] + ["2000"] * 12)
    sinking = _months(["0", "2400"] + ["0"] * 12)
    assert spread_average(totals, sinking, 12) == D("2200.00")
    assert spread_average(totals, sinking, 13) == D("2000.00")
