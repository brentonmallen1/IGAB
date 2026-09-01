"""`domain/card_timeline.py`: the per-month reserve series and its analysis.

Every series here is written by hand with round figures, checkable on paper —
per the card-scenario rule, deriving an expectation from the walk under test
would make the assertion a tautology. One case per breach cause: a payment
past the reserve, an uncapped residual, and a negative assignment.

The cumulative reserve is also pinned against `CardReserve.set_aside` itself,
over every card scenario — the timeline is a restatement of that number and
must never become a second opinion about it.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.card_timeline import card_timeline, first_breach, worst_months
from igab.domain.cards import CardReserve, card_funding, card_reserve
from igab.sample_budget.card_scenarios import ALL_SCENARIOS, to_funding_inputs

D = Decimal
JAN, FEB, MAR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)


def test_the_cumulative_reserve_is_the_signed_sum_of_the_legs():
    """+200 reserved in January; a 150 payment and a 100 residual in February
    land the reserve at -50. Checkable on one hand."""
    reserve = CardReserve(
        reservations={JAN: D("200")},
        payments={FEB: D("150")},
        residual={FEB: D("100")},
    )
    timeline = card_timeline(reserve, {}, {})
    assert [cm.set_aside for cm in timeline] == [D("200"), D("-50")]
    assert timeline[1].reserve_delta == D("-250")


def test_every_month_reads_the_same_position_rule_as_the_row():
    """The position beside each month is `card_position`, not a re-derivation:
    a -50 reserve against a -30 balance reads short_reserved 50, uncovered 30."""
    reserve = CardReserve(payments={JAN: D("50")})
    [cm] = card_timeline(reserve, {JAN: D("-30")}, {})
    assert cm.position.short_reserved == D("50")
    assert cm.position.uncovered == D("30")


def test_a_month_where_only_the_balance_moved_still_appears():
    """An unfiled charge touches no leg — precisely the month a diagnosis
    needs to see, so the timeline may not skip it."""
    reserve = CardReserve(reservations={JAN: D("100")})
    timeline = card_timeline(reserve, {FEB: D("-400")}, {})
    assert [cm.month for cm in timeline] == [JAN, FEB]
    assert timeline[1].set_aside == D("100")
    assert timeline[1].balance == D("-400")


class TestFirstBreach:
    def test_a_payment_past_the_reserve(self):
        """Reserved 200, paid 300: the breach is February and payments did it."""
        reserve = CardReserve(reservations={JAN: D("200")}, payments={FEB: D("300")})
        breach = first_breach(card_timeline(reserve, {}, {}))
        assert breach is not None
        assert breach.month == FEB
        assert (breach.set_aside_before, breach.set_aside_after) == (D("200"), D("-100"))
        assert breach.ranked_legs[0] == ("payments", D("-300"))

    def test_an_uncapped_residual(self):
        """Reserved 200, a 500 reimbursement in March releases nothing and
        drives the reserve to -300 — the REIMBURSED shape."""
        reserve = CardReserve(reservations={JAN: D("200")}, residual={MAR: D("500")})
        breach = first_breach(card_timeline(reserve, {}, {}))
        assert breach is not None
        assert breach.month == MAR
        assert breach.ranked_legs[0] == ("residual", D("-500"))

    def test_a_negative_assignment_past_the_reserve(self):
        """Assign 100, release 200: the third leg that can breach, and the one
        the identity's T2 bound does not currently allow for."""
        reserve = CardReserve(assignments={JAN: D("100"), FEB: D("-200")})
        breach = first_breach(card_timeline(reserve, {}, {}))
        assert breach is not None
        assert breach.month == FEB
        assert breach.ranked_legs[0] == ("assignments", D("-200"))

    def test_the_first_crossing_wins_over_a_deeper_later_one(self):
        reserve = CardReserve(
            reservations={JAN: D("100"), MAR: D("50")},
            payments={FEB: D("150"), MAR: D("500")},
        )
        breach = first_breach(card_timeline(reserve, {}, {}))
        assert breach is not None
        assert breach.month == FEB

    def test_a_negative_first_month_is_a_breach(self):
        reserve = CardReserve(payments={JAN: D("75")})
        breach = first_breach(card_timeline(reserve, {}, {}))
        assert breach is not None
        assert breach.month == JAN
        assert breach.set_aside_before == D("0")

    def test_a_reserve_that_never_goes_negative_has_none(self):
        reserve = CardReserve(reservations={JAN: D("200")}, payments={FEB: D("200")})
        assert first_breach(card_timeline(reserve, {}, {})) is None

    def test_zero_legs_are_omitted_from_the_ranking(self):
        reserve = CardReserve(payments={JAN: D("75")})
        breach = first_breach(card_timeline(reserve, {}, {}))
        assert breach is not None
        assert breach.ranked_legs == (("payments", D("-75")),)


class TestWorstMonths:
    def test_ranked_most_negative_first_and_capped(self):
        reserve = CardReserve(
            payments={JAN: D("10"), FEB: D("300")},
            residual={MAR: D("40")},
        )
        worst = worst_months(card_timeline(reserve, {}, {}), limit=2)
        assert [cm.month for cm in worst] == [FEB, MAR]

    def test_only_strictly_negative_months_qualify(self):
        reserve = CardReserve(reservations={JAN: D("200")})
        assert worst_months(card_timeline(reserve, {}, {})) == []


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=[s.slug for s in ALL_SCENARIOS])
def test_the_timeline_restates_set_aside_at_every_month(scenario):
    """Against the real walk, month by month: the timeline's cumulative figure
    must equal `CardReserve.set_aside` evaluated at each of its own months —
    a restatement, never a second opinion."""
    anchor = date(2026, 8, 15)
    inputs = to_funding_inputs(scenario, anchor)
    funding = card_funding(
        inputs.assignments, inputs.activity, inputs.outflows, inputs.card_categories
    )
    reserve = card_reserve(funding, scenario.card, inputs.payments)
    timeline = card_timeline(reserve, {}, funding.riding_by_card.get(scenario.card, {}))
    for cm in timeline:
        assert cm.set_aside == reserve.set_aside(cm.month)


def test_paid_ahead_then_caught_up_dips_exactly_where_the_scenario_says():
    """The scenario whose final position is unremarkable and whose story is
    the dip: -150 after the first month's statement payment, +50 after the
    next month reserved, 0 at the anchor. Hand-computed in the scenario;
    restated here against the timeline because the dip is the one claim the
    scenario's `expect` cannot carry."""
    anchor = date(2026, 8, 15)
    scenario = next(s for s in ALL_SCENARIOS if s.slug == "paid-ahead-then-caught-up")
    inputs = to_funding_inputs(scenario, anchor)
    funding = card_funding(
        inputs.assignments, inputs.activity, inputs.outflows, inputs.card_categories
    )
    reserve = card_reserve(funding, scenario.card, inputs.payments)
    timeline = card_timeline(reserve, {}, funding.riding_by_card.get(scenario.card, {}))
    assert [cm.set_aside for cm in timeline] == [D("-150"), D("50"), D("0")]
    breach = first_breach(timeline)
    assert breach is not None
    assert breach.month == timeline[0].month
    assert breach.ranked_legs[0] == ("payments", D("-250"))
