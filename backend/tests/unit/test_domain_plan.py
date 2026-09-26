"""`plan_outcome`: the one verdict Budget vs Actual and Plan vs Reality serve.

Budget vs Actual used to serve `assigned - spent` unfloored while Plan vs
Reality floored the plan, so a drained envelope was a red 300 overrun on one
screen and neutral on the other. Each case below is one the two used to
disagree on, or the baseline both must keep.
"""

from decimal import Decimal

from igab.domain.plan import (
    NO_EFFECT,
    PlanEffect,
    is_chronic,
    plan_effect,
    plan_outcome,
    total_variance,
)

D = Decimal


def test_a_drained_envelope_that_spent_nothing_is_on_plan():
    # 300 moved OUT of Car Repairs, nothing spent. Unfloored: variance -300,
    # over — which Budget vs Actual's chart drew red and ranked first.
    outcome = plan_outcome(D("-300"), D("0"), moved_in=D("0"), moved_out=D("0"))
    assert outcome.plan == D("0")
    assert outcome.variance == D("0")
    assert outcome.over is False
    # Floored to no plan, so there is no percentage of it.
    assert outcome.variance_pct is None


def test_real_spending_from_a_drained_envelope_is_over_by_what_was_spent():
    # Over by 120, not 420: the drain is not part of the overrun.
    outcome = plan_outcome(D("-300"), D("120"), moved_in=D("0"), moved_out=D("0"))
    assert outcome.variance == D("-120")
    assert outcome.over is True


def test_an_ordinary_plan_is_unchanged_by_the_floor():
    under = plan_outcome(D("500"), D("450"), moved_in=D("0"), moved_out=D("0"))
    assert (under.plan, under.variance, under.over) == (D("500"), D("50"), False)
    assert under.variance_pct == 10.0

    over = plan_outcome(D("100"), D("160"), moved_in=D("0"), moved_out=D("0"))
    assert (over.variance, over.over) == (D("-60"), True)
    assert over.variance_pct == -60.0


def test_spending_exactly_the_plan_is_not_over():
    assert plan_outcome(D("200"), D("200"), moved_in=D("0"), moved_out=D("0")).over is False


def test_no_plan_and_no_spending_is_quiet():
    outcome = plan_outcome(D("0"), D("0"), moved_in=D("0"), moved_out=D("0"))
    assert (outcome.variance, outcome.over, outcome.variance_pct) == (D("0"), False, None)


def test_spending_with_no_plan_is_over_with_no_percentage():
    # No denominator to measure against: None, not a division error — and not
    # 0.0, which Budget vs Actual printed as "0.0%", the figure for spending
    # a plan to the cent.
    outcome = plan_outcome(D("0"), D("40"), moved_in=D("0"), moved_out=D("0"))
    assert (outcome.variance, outcome.over, outcome.variance_pct) == (D("-40"), True, None)
    assert plan_outcome(D("40"), D("40"), moved_in=D("0"), moved_out=D("0")).variance_pct == 0.0


class TestTotalVariance:
    """Budget vs Actual's headline: the rows' floored verdicts, summed."""

    def test_a_drained_envelope_does_not_cancel_an_overspent_one(self):
        # 300 moved out of Car Repairs (nothing spent) and Dining 300 over its
        # 200. Raw assigned - spent: (-300 + 200) - 500 = -600; the rows say
        # on plan and 300 over.
        outcomes = [
            plan_outcome(D("-300"), D("0"), moved_in=D("0"), moved_out=D("0")),
            plan_outcome(D("200"), D("500"), moved_in=D("0"), moved_out=D("0")),
        ]
        assert total_variance(outcomes) == D("-300")

    def test_under_and_over_net(self):
        outcomes = [
            plan_outcome(D("500"), D("450"), moved_in=D("0"), moved_out=D("0")),
            plan_outcome(D("100"), D("160"), moved_in=D("0"), moved_out=D("0")),
        ]
        assert total_variance(outcomes) == D("-10")

    def test_spending_with_no_plan_counts_in_full(self):
        assert total_variance(
            [plan_outcome(D("0"), D("40"), moved_in=D("0"), moved_out=D("0"))]
        ) == D("-40")

    def test_nothing_is_on_plan(self):
        assert total_variance([]) == D("0")


class TestMoneyMovedIn:
    """A transfer or deposit into an envelope raises its plan — the mirror of
    the floor. Read as nothing, a 2,000 medical bill paid by 2,000 moved in
    from savings was a 2,000 overrun on all three plan reports while the
    budget page showed the envelope on plan."""

    def test_a_bill_paid_by_money_moved_in_is_on_plan(self):
        outcome = plan_outcome(D("0"), D("2000"), moved_in=D("2000"), moved_out=D("0"))
        assert (outcome.plan, outcome.variance, outcome.over) == (D("2000"), D("0"), False)

    def test_moved_in_money_beside_an_assignment_adds_to_it(self):
        outcome = plan_outcome(D("100"), D("2150"), moved_in=D("2000"), moved_out=D("0"))
        assert outcome.plan == D("2100")
        assert (outcome.variance, outcome.over) == (D("-50"), True)

    def test_it_refills_a_drained_envelope_to_no_more_than_it_brought(self):
        # 300 drained out, 200 moved back in: still no plan to measure.
        assert plan_outcome(D("-300"), D("0"), moved_in=D("200"), moved_out=D("0")).plan == D("0")
        assert plan_outcome(D("-300"), D("0"), moved_in=D("500"), moved_out=D("0")).plan == D("200")

    def test_refunds_beyond_the_spending_leave_room(self):
        # Net spent -30: the refunds beat the spending. Not over, and the
        # variance says the plan has more room than it started with.
        outcome = plan_outcome(D("100"), D("-30"), moved_in=D("0"), moved_out=D("0"))
        assert (outcome.variance, outcome.over) == (D("130"), False)


class TestMoneyMovedOut:
    """Money moved out of an envelope and not spent lowers its plan — the
    mirror of money moved in (owner's call, 2026-09-26). One floor at zero,
    over `assigned + moved_in - moved_out` as a whole."""

    def test_a_debt_payment_from_an_untagged_envelope_is_on_plan_not_underspent(self):
        """A Mortgage envelope assigned 1,500 and paid by a 1,500 principal
        transfer: it read 1,500 underspent every month."""
        outcome = plan_outcome(D("1500"), D("0"), moved_in=D("0"), moved_out=D("1500"))
        assert (outcome.plan, outcome.variance, outcome.over) == (D("0"), D("0"), False)

    def test_a_brokerage_transfer_leaves_the_rest_of_the_plan_to_spend(self):
        # 600 assigned, 400 sent to a brokerage, 180 spent: 20 left of 200.
        outcome = plan_outcome(D("600"), D("180"), moved_in=D("0"), moved_out=D("400"))
        assert (outcome.plan, outcome.variance, outcome.over) == (D("200"), D("20"), False)

    def test_spending_past_what_is_left_after_moving_out_is_over(self):
        outcome = plan_outcome(D("600"), D("300"), moved_in=D("0"), moved_out=D("400"))
        assert (outcome.plan, outcome.variance, outcome.over) == (D("200"), D("-100"), True)

    def test_moving_out_more_than_planned_floors_the_plan_at_zero(self):
        """A carried balance drawn down into a brokerage with nothing spent
        and nothing assigned this month: plan 0, on plan — never a negative
        plan every dollar of spending would overrun."""
        outcome = plan_outcome(D("0"), D("0"), moved_in=D("0"), moved_out=D("2000"))
        assert (outcome.plan, outcome.variance, outcome.over) == (D("0"), D("0"), False)

    def test_the_floor_is_over_the_sum_not_per_term(self):
        # 300 in, 500 out, 100 assigned: -100 floors to 0 — not 100 + 300.
        assert plan_outcome(D("100"), D("0"), moved_in=D("300"), moved_out=D("500")).plan == (
            D("0")
        )
        # 300 in, 100 out: 300 left of 100 + 300 - 100.
        assert plan_outcome(D("100"), D("0"), moved_in=D("300"), moved_out=D("100")).plan == (
            D("300")
        )

    def test_spending_beside_a_floored_plan_is_over(self):
        outcome = plan_outcome(D("0"), D("40"), moved_in=D("0"), moved_out=D("500"))
        assert (outcome.plan, outcome.variance, outcome.over) == (D("0"), D("-40"), True)

    def test_a_refund_beside_money_moved_out_leaves_room(self):
        outcome = plan_outcome(D("500"), D("-30"), moved_in=D("0"), moved_out=D("500"))
        assert (outcome.plan, outcome.variance, outcome.over) == (D("0"), D("30"), False)


class TestTheOverTolerance:
    """Over by at least $1 AND at least 1% of the plan. A mortgage assigned a
    few cents short read "over" three months running and was named chronic."""

    def test_cents_of_rounding_are_on_plan(self):
        outcome = plan_outcome(D("1500.00"), D("1500.27"), moved_in=D("0"), moved_out=D("0"))
        assert outcome.over is False
        # The arithmetic is still served; only the verdict is tolerant.
        assert outcome.variance == D("-0.27")

    def test_a_dollar_under_one_percent_of_a_big_plan_is_on_plan(self):
        # 5 over a 1,500 plan: past the dollar, short of the 15 that is 1%.
        assert plan_outcome(D("1500"), D("1505"), moved_in=D("0"), moved_out=D("0")).over is False

    def test_one_percent_under_a_dollar_is_on_plan(self):
        # 0.60 over a 50 plan: 1.2% of it, but short of the dollar.
        assert plan_outcome(D("50"), D("50.60"), moved_in=D("0"), moved_out=D("0")).over is False

    def test_both_at_once_is_over(self):
        assert plan_outcome(D("1500"), D("1515"), moved_in=D("0"), moved_out=D("0")).over is True
        assert plan_outcome(D("50"), D("51"), moved_in=D("0"), moved_out=D("0")).over is True

    def test_with_no_plan_a_dollar_is_over(self):
        assert plan_outcome(D("0"), D("1"), moved_in=D("0"), moved_out=D("0")).over is True
        assert plan_outcome(D("0"), D("0.99"), moved_in=D("0"), moved_out=D("0")).over is False


class TestIsChronic:
    def test_three_recent_months_over_is_chronic(self):
        assert is_chronic(3, sinking_fund=False) is True
        assert is_chronic(2, sinking_fund=False) is False

    def test_a_sinking_fund_never_is(self):
        """Months of saving and one month of paying the bill is the plan
        working; four quarterly tax payments in six months named the most
        disciplined envelope the household's worst habit."""
        assert is_chronic(6, sinking_fund=True) is False


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
