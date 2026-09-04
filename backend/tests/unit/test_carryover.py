"""The zero floor between months, which is the whole rule.

A running total gets every one of these cases wrong in the same direction:
it carries overspending forward that the budget already covered from To Be
Assigned, so the category reads permanently low.
"""

from datetime import date
from decimal import Decimal

from igab.domain.carryover import available_at, available_through, next_carryover

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


class TestThePiecesTheCardWalkShares:
    """`next_carryover` and `available_at` exist so `domain.cards` can run the
    same simulation with card corrections folded into each month's activity.
    Stated twice, the floor and the read would drift, and the card walk's whole
    claim is that its answer is this rule.
    """

    def test_the_floor_between_months_is_stated_once(self):
        assert next_carryover(D("50")) == D("50")
        assert next_carryover(D("0")) == D("0")
        # The write-off: a negative month hands the next one nothing.
        assert next_carryover(D("-50")) == D("0")

    def test_available_at_reads_the_viewed_month_out_of_a_supplied_series(self):
        series = {JAN: D("100"), FEB: D("-30"), MAR: D("20")}
        # The month with its own data keeps its raw value, negative included.
        assert available_at(series, FEB) == D("-30")
        assert available_at(series, MAR) == D("20")

    def test_available_at_floors_the_carryover_for_a_month_with_no_data(self):
        assert available_at({JAN: D("-30")}, FEB) == D("0")
        assert available_at({JAN: D("30")}, FEB) == D("30")
        assert available_at({}, JAN) == D("0")

    def test_available_at_ignores_months_after_the_one_asked_for(self):
        # The card walk holds the whole history so it can carry reservations
        # forward; asking for an early month must not see the later ones.
        series = {JAN: D("10"), MAR: D("999")}
        assert available_at(series, FEB) == D("10")


class TestQuantizeCents:
    """The rounding convention, named rather than inherited.

    Twenty-two sites took their rounding mode from the global decimal context.
    That gave the right answer — half-even is the default — but by accident:
    anything setting `getcontext().rounding` would have moved money display
    across every report with nothing to notice it.
    """

    def test_rounds_half_to_even(self):
        from igab.domain.money import quantize_cents

        # The property that makes it unbiased over a long column of figures.
        assert quantize_cents(D("0.125")) == D("0.12")
        assert quantize_cents(D("0.135")) == D("0.14")

    def test_does_not_drag_upward_like_half_up(self):
        from igab.domain.money import quantize_cents

        halves = [D("0.005"), D("0.015"), D("0.025"), D("0.035")]
        # Half-up would total 0.10; half-even splits the ties.
        assert sum((quantize_cents(v) for v in halves), D("0")) == D("0.08")

    def test_leaves_exact_cents_alone(self):
        from igab.domain.money import quantize_cents

        for value in ("0.00", "1.23", "-4.56", "999999.99"):
            assert quantize_cents(D(value)) == D(value)

    def test_handles_negatives_symmetrically(self):
        from igab.domain.money import quantize_cents

        assert quantize_cents(D("-0.125")) == D("-0.12")
        assert quantize_cents(D("-0.135")) == D("-0.14")

    def test_is_independent_of_the_global_context(self):
        import decimal

        from igab.domain.money import quantize_cents

        original = decimal.getcontext().rounding
        try:
            decimal.getcontext().rounding = decimal.ROUND_UP
            # The bare `.quantize(Decimal("0.01"))` this replaced would return
            # 0.13 here. That is the hazard being removed.
            assert quantize_cents(D("0.125")) == D("0.12")
        finally:
            decimal.getcontext().rounding = original


class TestTheImportAnchorOpening:
    """`monthly_end_balances(opening=...)` — the walk seeded at YNAB's B−1
    figure, with everything earlier truncated inside the domain."""

    def test_none_is_byte_identical(self):
        asg, act = {JAN: D("100"), MAR: D("20")}, {FEB: D("-30")}
        from igab.domain.carryover import monthly_end_balances

        assert monthly_end_balances(asg, act, opening=None) == monthly_end_balances(asg, act)

    def test_the_opening_is_emitted_raw_and_floored_forward(self):
        from igab.domain.carryover import monthly_end_balances

        out = monthly_end_balances({}, {FEB: D("-10")}, opening=(JAN, D("-25")))
        # January shows YNAB's own (negative) figure; February starts at the
        # floored zero, exactly as any month end would.
        assert out == {JAN: D("-25"), FEB: D("-10")}

    def test_months_at_or_before_the_opening_are_truncated(self):
        from igab.domain.carryover import monthly_end_balances

        out = monthly_end_balances({JAN: D("999")}, {JAN: D("-500")}, opening=(FEB, D("40")))
        # January's data is history the seed already accounts for.
        assert out == {FEB: D("40")}

    def test_a_zero_opening_still_truncates(self):
        from igab.domain.carryover import monthly_end_balances

        out = monthly_end_balances({JAN: D("999")}, {MAR: D("-5")}, opening=(FEB, D("0")))
        assert out == {MAR: D("-5")}

    def test_available_through_reads_the_anchor(self):
        assert available_through({}, {}, FEB, opening=(FEB, D("-25"))) == D("-25")
        assert available_through({}, {}, MAR, opening=(FEB, D("-25"))) == D("0")
        assert available_through({MAR: D("10")}, {}, MAR, opening=(FEB, D("40"))) == D("50")

    def test_a_month_before_the_anchor_reads_zero(self):
        # The UI clamps navigation at B; a service caller asking anyway gets
        # a calm zero, never a re-derivation.
        assert available_through({JAN: D("777")}, {}, JAN, opening=(FEB, D("40"))) == D("0")
