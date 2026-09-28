"""`envelope_outcome` and `across_months`: the one verdict every plan-vs-actual
report serves — what an envelope had, spent and had left, carryover counted.

The report used to judge each month's assignment alone, so an envelope funded
once and spent across several months read "over" in each. Each case below is
one that verdict got wrong, or the baseline both must keep. Figures are
written by hand, never derived from the function under test.
"""

from decimal import Decimal

from igab.domain.plan import (
    NO_EFFECT,
    EnvelopeOutcome,
    PlanEffect,
    across_months,
    envelope_outcome,
    is_chronic,
    plan_effect,
)

D = Decimal


def month(
    carried_in="0", assigned="0", spent="0", moved_in="0", moved_out="0", left=None
) -> EnvelopeOutcome:
    return envelope_outcome(
        carried_in=None if carried_in is None else D(carried_in),
        assigned=D(assigned),
        moved_in=D(moved_in),
        moved_out=D(moved_out),
        spent=D(spent),
        left=None if left is None else D(left),
    )


class TestAMonth:
    def test_spending_a_balance_carried_in_is_not_over(self):
        # Nothing assigned this month; 400 carried in from January's 600.
        o = month(carried_in="400", spent="100", left="300")
        assert (o.funded, o.left, o.overspent, o.over) == (D("400"), D("300"), D("0"), False)

    def test_spending_past_what_it_had_is_over_by_the_shortfall(self):
        o = month(carried_in="50", assigned="100", spent="200", left="-50")
        assert (o.funded, o.overspent, o.over) == (D("150"), D("50"), True)

    def test_spending_exactly_what_it_had_is_not_over(self):
        o = month(carried_in="20", assigned="80", spent="100", left="0")
        assert (o.overspent, o.over) == (D("0"), False)

    def test_nothing_at_all_is_quiet(self):
        o = month(left="0")
        assert (o.funded, o.left, o.overspent, o.over) == (D("0"),) * 3 + (False,)

    def test_money_moved_in_funds_it(self):
        # A 2,000 bill paid by 2,000 moved in from savings.
        o = month(moved_in="2000", spent="2000", left="0")
        assert (o.funded, o.over) == (D("2000"), False)

    def test_money_moved_out_unfunds_it(self):
        # 1,500 assigned and paid out as a principal transfer: on plan.
        o = month(assigned="1500", moved_out="1500", left="0")
        assert (o.funded, o.left, o.over) == (D("0"), D("0"), False)

    def test_moving_out_a_balance_carried_in_is_not_over(self):
        # case A, one month on: February's 1,000 moved out in March.
        o = month(carried_in="1000", moved_out="1000", left="0")
        assert (o.funded, o.over) == (D("0"), False)

    def test_moving_out_more_than_it_had_is_over(self):
        o = month(carried_in="100", moved_out="300", left="-200")
        assert (o.funded, o.overspent, o.over) == (D("-200"), D("200"), True)

    def test_refunds_beating_spending_leave_more(self):
        o = month(assigned="100", spent="-30", left="130")
        assert (o.left, o.over) == (D("130"), False)

    def test_a_negative_assignment_takes_money_back(self):
        o = month(carried_in="300", assigned="-300", left="0")
        assert (o.funded, o.over) == (D("0"), False)


class TestLeftIsTheBudgetPages:
    """`left` is served (the budget page's Available); `other` is whatever
    the page counts that the ledger does not."""

    def test_an_ordinary_envelope_has_no_other(self):
        o = month(carried_in="100", assigned="50", spent="30", left="120")
        assert o.other == D("0")

    def test_a_pending_row_the_ledger_skips_is_other(self):
        # The page's Available nets a pending 40; the ledger reads posted only.
        o = month(assigned="100", spent="30", left="30")
        assert (o.other, o.left) == (D("-40"), D("30"))

    def test_the_verdict_reads_the_pages_balance_not_the_ledgers(self):
        # Ledger says 70 left; the page says 5 short — the page wins.
        o = month(assigned="100", spent="30", left="-5")
        assert (o.overspent, o.over) == (D("5"), True)

    def test_a_month_with_no_page_figure_is_walked_from_the_ledger(self):
        o = month(carried_in=None, assigned="100", spent="130", left=None)
        assert (o.carried_in, o.left, o.other, o.estimated) == (None, D("-30"), D("0"), True)
        assert o.over is True

    def test_a_month_with_a_page_figure_is_not_estimated(self):
        assert month(assigned="10", left="10").estimated is False


class TestTheOverTolerance:
    """Negative by a dollar AND 1% of what it had — rounding is not a habit."""

    def test_cents_of_rounding_are_not_over(self):
        o = month(assigned="1499.97", spent="1500", left="-0.03")
        assert (o.overspent, o.over) == (D("0.03"), False)

    def test_a_dollar_under_one_percent_of_a_big_envelope_is_not_over(self):
        assert month(assigned="500", spent="504", left="-4").over is False

    def test_one_percent_under_a_dollar_is_not_over(self):
        assert month(assigned="50", spent="50.60", left="-0.60").over is False

    def test_both_at_once_is_over(self):
        assert month(assigned="100", spent="102", left="-2").over is True

    def test_with_nothing_in_it_a_dollar_is_over(self):
        assert month(spent="1", left="-1").over is True

    def test_a_negative_funding_is_no_share_to_forgive(self):
        # Moved out past what it had: the share floor reads zero, not negative.
        assert month(moved_out="1", left="-1").over is True


class TestAcrossMonths:
    """A span of months walked in order: started with, funded, spent, and
    what Ready to Assign covered, ending at the last month's floored left."""

    @staticmethod
    def _identity(o: EnvelopeOutcome) -> None:
        assert o.funded - o.spent + o.other + o.overspent == o.left

    def test_funded_once_and_spent_down_is_on_plan(self):
        # case E: 600 in January, 100 a month for six months.
        months = [month("0", "600", "100", left="500")] + [
            month(str(600 - 100 * i), "0", "100", left=str(500 - 100 * i)) for i in range(1, 6)
        ]
        span = across_months(months)
        assert (span.funded, span.spent, span.left, span.overspent) == (
            D("600"),
            D("600"),
            D("0"),
            D("0"),
        )
        assert span.over is False
        self._identity(span)

    def test_funded_is_not_the_months_funded_summed(self):
        # Summing each month's funded would count January's 600 six times.
        a = month("0", "600", "100", left="500")
        b = month("500", "0", "100", left="400")
        assert across_months([a, b]).funded == D("600")

    def test_it_starts_from_what_the_first_month_carried_in(self):
        span = across_months([month("250", "100", "300", left="50")])
        assert (span.carried_in, span.funded, span.left) == (D("250"), D("350"), D("50"))

    def test_a_month_overspent_is_covered_and_the_next_starts_at_zero(self):
        # June 100 short (Ready to Assign covers it); July starts from zero.
        june = month("0", "200", "300", left="-100")
        july = month("0", "200", "150", left="50")
        span = across_months([june, july])
        assert (span.funded, span.spent, span.overspent, span.left) == (
            D("400"),
            D("450"),
            D("100"),
            D("50"),
        )
        assert span.over is True
        self._identity(span)

    def test_a_span_ending_overspent_leaves_nothing_and_counts_the_shortfall(self):
        span = across_months([month("0", "100", "160", left="-60")])
        assert (span.left, span.overspent) == (D("0"), D("60"))
        self._identity(span)

    def test_saving_builds_left_not_under(self):
        # case D: 200 a month, never drawn.
        months = [month(str(200 * i), "200", left=str(200 * (i + 1))) for i in range(6)]
        span = across_months(months)
        assert (span.funded, span.left, span.overspent, span.over) == (
            D("1200"),
            D("1200"),
            D("0"),
            False,
        )

    def test_other_is_summed_and_kept_in_the_identity(self):
        span = across_months([month("0", "100", "30", left="30"), month("30", "0", "0", left="30")])
        assert span.other == D("-40")
        self._identity(span)

    def test_an_unknown_carry_in_counts_as_zero_and_is_said(self):
        span = across_months([month(None, "100", "40", left="60")])
        assert (span.carried_in, span.funded) == (None, D("100"))

    def test_any_estimated_month_makes_the_span_estimated(self):
        span = across_months([month(None, "10", left=None), month("10", left="10")])
        assert span.estimated is True

    def test_no_months_is_nothing(self):
        span = across_months([])
        assert (span.funded, span.spent, span.left, span.overspent, span.over) == (
            (D("0"),) * 4 + (False,)
        )

    def test_the_span_is_judged_by_the_months_tolerance(self):
        # Three months each 40 cents short: 1.20 covered on 300 funded.
        months = [month("0", "100", "100.40", left="-0.40") for _ in range(3)]
        span = across_months(months)
        assert (span.overspent, span.over) == (D("1.20"), False)


class TestIsChronic:
    def test_three_recent_months_over_is_chronic(self):
        assert is_chronic(3) is True
        assert is_chronic(2) is False

    def test_no_tag_exempts_it(self):
        # A sinking fund paying its bill no longer goes negative, so it never
        # reaches the count; one that does is overspent, tagged or not.
        assert is_chronic(6) is True


class TestPlanEffect:
    """What one row filed to a planned envelope does to its plan report."""

    def test_spending_out_is_spent(self):
        assert plan_effect(D("-80"), "spending", savings_envelope=False) == PlanEffect(
            D("80"), D("0"), D("0")
        )

    def test_a_refund_lowers_spent(self):
        """It used to be dropped: `amount < 0` in the row shape, so a returned
        purchase read as the whole purchase."""
        assert plan_effect(D("30"), "spending", savings_envelope=False) == PlanEffect(
            D("-30"), D("0"), D("0")
        )

    def test_a_transfer_in_from_savings_raises_the_plan(self):
        assert plan_effect(D("2000"), "savings", savings_envelope=False) == PlanEffect(
            D("0"), D("2000"), D("0")
        )

    def test_a_deposit_into_a_savings_envelope_raises_the_plan(self):
        # A bonus filed to a sent-out Savings envelope classes SAVINGS.
        assert plan_effect(D("500"), "savings", savings_envelope=True) == PlanEffect(
            D("0"), D("500"), D("0")
        )

    def test_a_loan_draw_spent_through_an_envelope_raises_the_plan(self):
        assert plan_effect(D("900"), "debt_principal", savings_envelope=False) == PlanEffect(
            D("0"), D("900"), D("0")
        )

    def test_money_leaving_a_savings_envelope_is_spent_whatever_its_class(self):
        assert plan_effect(D("-390"), "savings", savings_envelope=True) == PlanEffect(
            D("390"), D("0"), D("0")
        )

    def test_a_brokerage_transfer_out_of_an_untagged_envelope_lowers_the_plan(self):
        """Saving the plan never meant as spending — so not spent, but not
        left unspent either. It used to be NO_EFFECT, and the envelope read
        underspent by the whole transfer."""
        assert plan_effect(D("-200"), "savings", savings_envelope=False) == PlanEffect(
            D("0"), D("0"), D("200")
        )

    def test_a_debt_principal_payment_from_an_untagged_envelope_lowers_the_plan(self):
        """A Mortgage envelope nobody tagged Debt principal, paid by a
        principal transfer to the tracked loan."""
        assert plan_effect(D("-900"), "debt_principal", savings_envelope=False) == PlanEffect(
            D("0"), D("0"), D("900")
        )

    def test_other_non_spending_outflows_lower_the_plan_too(self):
        for cls in ("transfer_internal", "investment_return", "income"):
            assert plan_effect(D("-50"), cls, savings_envelope=False) == PlanEffect(
                D("0"), D("0"), D("50")
            ), cls

    def test_money_leaving_a_savings_envelope_is_still_spent_not_moved_out(self):
        """The exception stands: a savings envelope's outflow is the spending
        its plan was for (#182), so it counts as spent, never as moved out."""
        for cls in ("savings", "debt_principal"):
            effect = plan_effect(D("-390"), cls, savings_envelope=True)
            assert effect == PlanEffect(D("390"), D("0"), D("0")), cls

    def test_a_starting_balance_moves_neither_side(self):
        assert plan_effect(D("1000"), "opening_balance", savings_envelope=False) == NO_EFFECT
        assert plan_effect(D("-1000"), "opening_balance", savings_envelope=False) == NO_EFFECT
        assert plan_effect(D("1000"), "opening_balance", savings_envelope=True) == NO_EFFECT
        # Not "money leaving a savings envelope" either: counting begins there.
        assert plan_effect(D("-1000"), "opening_balance", savings_envelope=True) == NO_EFFECT

    def test_zero_does_nothing(self):
        assert plan_effect(D("0"), "savings", savings_envelope=False) == NO_EFFECT

    def test_it_is_linear_so_a_bucket_may_be_summed(self):
        rows = [D("-40"), D("-60")]
        one = plan_effect(sum(rows, D("0")), "spending", savings_envelope=False)
        each = [plan_effect(a, "spending", savings_envelope=False) for a in rows]
        assert one.spent == sum((e.spent for e in each), D("0"))

    def test_moved_out_is_linear_within_a_same_sign_bucket(self):
        rows = [D("-150"), D("-350")]
        one = plan_effect(sum(rows, D("0")), "savings", savings_envelope=False)
        each = [plan_effect(a, "savings", savings_envelope=False) for a in rows]
        assert one.moved_out == sum((e.moved_out for e in each), D("0")) == D("500")
