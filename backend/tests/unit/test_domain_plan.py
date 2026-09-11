"""`plan_outcome`: the one verdict Budget vs Actual and Plan vs Reality serve.

Budget vs Actual used to serve `assigned - spent` unfloored while Plan vs
Reality floored the plan, so a drained envelope was a red 300 overrun on one
screen and neutral on the other. Each case below is one the two used to
disagree on, or the baseline both must keep.
"""

from decimal import Decimal

from igab.domain.plan import plan_outcome

D = Decimal


def test_a_drained_envelope_that_spent_nothing_is_on_plan():
    # 300 moved OUT of Car Repairs, nothing spent. Unfloored: variance -300,
    # over — which Budget vs Actual's chart drew red and ranked first.
    outcome = plan_outcome(D("-300"), D("0"))
    assert outcome.plan == D("0")
    assert outcome.variance == D("0")
    assert outcome.over is False
    assert outcome.variance_pct == 0.0


def test_real_spending_from_a_drained_envelope_is_over_by_what_was_spent():
    # Over by 120, not 420: the drain is not part of the overrun.
    outcome = plan_outcome(D("-300"), D("120"))
    assert outcome.variance == D("-120")
    assert outcome.over is True


def test_an_ordinary_plan_is_unchanged_by_the_floor():
    under = plan_outcome(D("500"), D("450"))
    assert (under.plan, under.variance, under.over) == (D("500"), D("50"), False)
    assert under.variance_pct == 10.0

    over = plan_outcome(D("100"), D("160"))
    assert (over.variance, over.over) == (D("-60"), True)
    assert over.variance_pct == -60.0


def test_spending_exactly_the_plan_is_not_over():
    assert plan_outcome(D("200"), D("200")).over is False


def test_no_plan_and_no_spending_is_quiet():
    outcome = plan_outcome(D("0"), D("0"))
    assert (outcome.variance, outcome.over, outcome.variance_pct) == (D("0"), False, 0.0)


def test_spending_with_no_plan_is_over_with_no_percentage():
    # No denominator to measure against: 0, not a division error.
    outcome = plan_outcome(D("0"), D("40"))
    assert (outcome.variance, outcome.over, outcome.variance_pct) == (D("-40"), True, 0.0)
