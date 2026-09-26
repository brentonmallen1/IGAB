"""Spreading sinking-fund bills over twelve months: the pure arithmetic.

`guide.concepts.essentials_at` is the headline every surface quotes and every
point of the coverage series; `spread_average` is its spread half. Figures are
round enough to check on paper: $2,000 a month of ordinary essentials and a
$2,400 yearly premium filed to a Long-term expense category.
"""

from datetime import date
from decimal import Decimal as D

import pytest

from igab.guide.concepts import (
    ESSENTIALS_MONTHS,
    EssentialsMonthly,
    essentials_at,
    spread_average,
    trailing_average,
)

#: Twelve complete months, January to December, as the service reads them.
MONTHS = [date(2025, m, 1) for m in range(1, 13)]
ORDINARY = D("2000.00")
PREMIUM = D("2400.00")


def year(bill_month: int | None = None, ordinary: D = ORDINARY):
    """Twelve months of ordinary essentials, the premium in `bill_month`."""
    totals = [ordinary] * 12
    sinking = [D("0")] * 12
    if bill_month is not None:
        totals[bill_month] += PREMIUM
        sinking[bill_month] = PREMIUM
    return MONTHS, totals, sinking


def test_no_sinking_funds_spread_equals_as_paid():
    """With no sinking-fund rows the two figures agree to the cent — including
    on a total that does not divide by three evenly."""
    for ordinary in (D("0"), ORDINARY, D("333.34"), D("0.01")):
        m = essentials_at(*year(ordinary=ordinary), 11, spread_on=True)
        assert m.spread == m.as_paid
        assert m.monthly == m.as_paid
    months, _, sinking = year()
    uneven = [D("0")] * 9 + [D("1000.00"), D("0"), D("0")]
    assert essentials_at(months, uneven, sinking, 11, spread_on=True).as_paid == D("333.33")


def test_an_annual_bill_is_a_twelfth_inside_or_outside_the_three_months():
    """Paid last month the premium is inside the three complete months: as
    paid reads (6,000 + 2,400) / 3 = 2,800, spread 2,000 + 200 = 2,200. Paid
    in March it is outside: as paid 2,000, spread still 2,200."""
    inside = essentials_at(*year(11), 11, spread_on=True)
    assert (inside.as_paid, inside.spread) == (D("2800.00"), D("2200.00"))
    outside = essentials_at(*year(2), 11, spread_on=True)
    assert (outside.as_paid, outside.spread) == (D("2000.00"), D("2200.00"))


def test_monthly_follows_the_setting():
    assert essentials_at(*year(11), 11, spread_on=True).monthly == D("2200.00")
    off = essentials_at(*year(11), 11, spread_on=False)
    assert off.monthly == D("2800.00")
    # Both figures are served either way; only the choice moves.
    assert (off.as_paid, off.spread, off.spread_on) == (D("2800.00"), D("2200.00"), False)


def test_a_refund_to_a_sinking_fund_lowers_the_spread_part():
    """A $400 partial refund of the premium, a month later: $400 less spread,
    a twelfth of it a month."""
    months, totals, sinking = year(5)
    totals[6] -= D("400.00")
    sinking[6] = D("-400.00")
    assert essentials_at(months, totals, sinking, 11, spread_on=True).spread == D("2166.67")


class TestTheHeadlineIsThreeCompleteMonths:
    """D6: the essentials figure is the last three COMPLETE months, so a
    monthly bill is in it exactly three times whatever the day."""

    def test_it_averages_exactly_the_last_three(self):
        # Only the newest three months are read: a costly spring is gone.
        months, totals, sinking = year()
        totals[:9] = [D("9000.00")] * 9
        assert ESSENTIALS_MONTHS == 3
        assert essentials_at(months, totals, sinking, 11, spread_on=False).as_paid == ORDINARY

    def test_it_names_the_months_it_averaged(self):
        m = essentials_at(*year(), 11, spread_on=False)
        assert (m.window_start, m.window_end) == (date(2025, 10, 1), date(2025, 12, 31))

    def test_a_young_budget_divides_by_the_months_it_has(self):
        # History from November: two complete months, averaged over two — not
        # divided by three as the ninety-day figure was.
        months, totals, sinking = year()
        totals[:10] = [D("0")] * 10
        m = essentials_at(months, totals, sinking, 11, first_data=10, spread_on=False)
        assert m.as_paid == ORDINARY
        assert (m.window_start, m.window_end) == (date(2025, 11, 1), date(2025, 12, 31))

    def test_no_complete_month_measures_nothing(self):
        # History starting this month: no complete month to average.
        m = essentials_at(*year(), 11, first_data=12, spread_on=True)
        assert (m.as_paid, m.spread) == (D("0"), D("0.00"))
        assert (m.window_start, m.window_end) == (None, None)

    @pytest.mark.parametrize("index", range(2, 12))
    def test_a_steady_mortgage_reads_the_same_at_every_month(self, index):
        # The rolling ninety days jumped by a whole payment the day one
        # entered or left the window. Monthly buckets hold it three times.
        months, totals, sinking = year(ordinary=D("3000.00"))
        assert essentials_at(months, totals, sinking, index, spread_on=False).as_paid == D(
            "3000.00"
        )

    def test_the_default_figures_are_a_dataclass_value(self):
        m = essentials_at(*year(), 11, spread_on=False)
        assert m == EssentialsMonthly(
            ORDINARY,
            ORDINARY,
            spread_on=False,
            window_start=date(2025, 10, 1),
            window_end=date(2025, 12, 31),
        )


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
