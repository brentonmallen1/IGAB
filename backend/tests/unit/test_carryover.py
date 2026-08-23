"""The zero floor between months, which is the whole rule.

A running total gets every one of these cases wrong in the same direction:
it carries overspending forward that the budget already covered from To Be
Assigned, so the category reads permanently low.
"""

from datetime import date
from decimal import Decimal

from igab.domain.carryover import available_through

JAN, FEB, MAR, APR = (date(2026, m, 1) for m in (1, 2, 3, 4))
D = Decimal


class TestTheSimpleCases:
    def test_no_data_is_zero(self):
        assert available_through({}, {}, MAR) == D("0")

    def test_assignment_with_no_spending(self):
        assert available_through({JAN: D("100")}, {}, JAN) == D("100")

    def test_spending_reduces_available(self):
        assert available_through({JAN: D("100")}, {JAN: D("-30")}, JAN) == D("70")

    def test_unspent_money_carries_forward(self):
        assert available_through({JAN: D("100")}, {}, FEB) == D("100")

    def test_carryover_accumulates_across_months(self):
        assert available_through({JAN: D("100"), FEB: D("100")}, {}, FEB) == D("200")


class TestTheZeroFloor:
    def test_the_viewed_month_may_show_negative(self):
        # Overspending is visible in the month it happened — that is the point.
        assert available_through({JAN: D("100")}, {JAN: D("-150")}, JAN) == D("-50")

    def test_the_overspend_does_not_carry_into_the_next_month(self):
        # TBA absorbed the -50; February starts at zero, not at -50.
        assert available_through({JAN: D("100")}, {JAN: D("-150")}, FEB) == D("0")

    def test_a_later_assignment_is_not_eaten_by_an_earlier_overspend(self):
        # The running-total answer here is 50. The correct answer is 100.
        assert available_through({JAN: D("100"), FEB: D("100")}, {JAN: D("-150")}, FEB) == D("100")

    def test_the_floor_applies_at_every_boundary_it_crosses(self):
        assert available_through(
            {JAN: D("10"), FEB: D("10")}, {JAN: D("-100"), FEB: D("-100")}, MAR
        ) == D("0")

    def test_an_exactly_zero_month_carries_zero(self):
        assert available_through({JAN: D("100")}, {JAN: D("-100")}, FEB) == D("0")


class TestMonthsWithNoDataOfTheirOwn:
    def test_a_gap_month_does_not_reset_the_carryover(self):
        # February has neither assignment nor activity. It is skipped, not
        # treated as a month that zeroed the balance.
        assert available_through({JAN: D("100")}, {MAR: D("-25")}, MAR) == D("75")

    def test_viewing_a_month_with_no_data_shows_the_carryover(self):
        assert available_through({JAN: D("100")}, {}, APR) == D("100")

    def test_viewing_a_month_before_any_data_is_zero(self):
        assert available_through({MAR: D("100")}, {}, JAN) == D("0")


class TestFutureMonthsAreNotCounted:
    def test_an_assignment_for_a_later_month_is_ignored(self):
        # The bug the guide had: pre-assigning October inflated today's number.
        assert available_through({JAN: D("100"), APR: D("500")}, {}, JAN) == D("100")

    def test_activity_in_a_later_month_is_ignored(self):
        assert available_through({JAN: D("100")}, {APR: D("-500")}, JAN) == D("100")


class TestAmountEdges:
    def test_activity_can_be_positive(self):
        # A refund into a category is activity like any other.
        assert available_through({JAN: D("100")}, {JAN: D("25")}, JAN) == D("125")

    def test_income_only_month_with_no_assignment(self):
        assert available_through({}, {JAN: D("40")}, JAN) == D("40")

    def test_spending_with_no_assignment_shows_negative_then_floors(self):
        assert available_through({}, {JAN: D("-40")}, JAN) == D("-40")
        assert available_through({}, {JAN: D("-40")}, FEB) == D("0")

    def test_cents_are_exact(self):
        assert available_through({JAN: D("0.10"), FEB: D("0.20")}, {JAN: D("-0.05")}, FEB) == D(
            "0.25"
        )

    def test_a_negative_assignment_is_honoured(self):
        # Pulling money back out of a category is a real operation.
        assert available_through({JAN: D("100"), FEB: D("-40")}, {}, FEB) == D("60")
