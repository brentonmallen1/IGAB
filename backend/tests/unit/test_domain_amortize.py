"""`spread_forward`: each charge over the months it pays for.

Every expectation is written by hand, round enough to check on paper. Two
wrong spreading rules used to pass the whole suite — a fixed period (window ÷
number of charges) and a next-charge lookup that leaked across categories —
because every case had one category and equal gaps. The cases below are the
ones that tell those apart.
"""

import pytest

from igab.domain.amortize import spread_forward

N = None


def cents(values):
    return [None if v is None else round(v, 2) for v in values]


class TestEveryPhaseReadsFlat:
    """A 600 bill every six months reads 100 a month wherever the window
    starts. It used to read flat only when a charge fell in the window's first
    month; the Feb+Aug phase of a Sep–Aug window read 0 to 600, the raw range."""

    @pytest.mark.parametrize("first", range(6))
    def test_a_six_monthly_bill_in_every_phase(self, first):
        totals = [0.0] * 12
        totals[first] = 600.0
        totals[first + 6] = 600.0

        assert spread_forward(totals) == [N] * first + [100.0] * (12 - first)

    @pytest.mark.parametrize("first", range(3))
    def test_a_quarterly_bill_in_every_phase(self, first):
        # Nov/Feb/May/Aug on a Sep–Aug grid is first=2: it read 0–300.
        totals = [300.0 if i >= first and (i - first) % 3 == 0 else 0.0 for i in range(12)]
        assert spread_forward(totals) == [N] * first + [100.0] * (12 - first)

    def test_a_bimonthly_bill_charged_in_the_odd_months(self):
        totals = [0.0, 200.0] * 6
        assert spread_forward(totals) == [N] + [100.0] * 11


class TestTheShapeOfTheSpread:
    def test_unequal_gaps_spread_to_the_next_charge(self):
        # 900 in Jan, Apr and Oct. Jan covers Jan–Mar, Apr covers Apr–Sep,
        # and Oct keeps its prior six-month rhythm: 150 over Oct–Dec.
        # A fixed-period rule (12 ÷ 3 charges) reads 0 in some months.
        totals = [900.0, 0, 0, 900.0, 0, 0, 0, 0, 0, 900.0, 0, 0]
        assert spread_forward(totals) == [300.0] * 3 + [150.0] * 9

    def test_the_last_charge_keeps_its_rhythm_rather_than_the_leftover_months(self):
        # A charge in the grid's last month used to read at full size.
        totals = [0.0, 600.0, 0, 0, 0, 0, 0, 600.0]
        assert spread_forward(totals) == [N] + [100.0] * 7

    def test_a_bill_that_stopped_reads_zero_after_its_last_gap(self):
        totals = [50.0, 50.0, 50.0, 0, 0, 0]
        assert spread_forward(totals) == [50.0, 50.0, 50.0, 0.0, 0.0, 0.0]

    def test_a_lone_charge_spreads_to_the_end_of_the_grid(self):
        totals = [0.0, 0, 0, 0, 0, 0, 600.0, 0, 0, 0, 0, 0]
        assert spread_forward(totals) == [N] * 6 + [100.0] * 6

    def test_a_lone_charge_in_the_last_month_is_its_own_month(self):
        assert spread_forward([0.0, 0.0, 250.0]) == [N, N, 250.0]

    def test_a_split_that_does_not_divide_evenly_keeps_every_cent(self):
        # 1,000 in Jan and 1,000 in Apr: 333.33 a month, and the three shares
        # of the first charge still sum to the charge.
        out = spread_forward([1000.0, 0, 0, 1000.0, 0, 0])
        assert cents(out) == [333.33] * 6
        assert sum(out[:3]) == pytest.approx(1000.0, abs=0.005)

    def test_a_rate_that_really_changed_still_shows(self):
        totals = [600.0, 0, 0, 0, 0, 0, 1800.0, 0, 0, 0, 0, 0]
        assert spread_forward(totals) == [100.0] * 6 + [300.0] * 6


class TestNothingToSpread:
    def test_no_charges_is_all_unknown(self):
        assert spread_forward([0.0, 0.0, 0.0]) == [N, N, N]

    def test_an_empty_grid(self):
        assert spread_forward([]) == []

    def test_a_charge_every_month_is_unchanged(self):
        totals = [120.0, 80.0, 100.0]
        assert spread_forward(totals) == totals
