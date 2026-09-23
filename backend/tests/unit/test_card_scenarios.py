"""Every card scenario, checked against the pure domain.

One of three suites over `ALL_SCENARIOS` — this one, the integration suite in
`tests/integration/test_card_scenarios.py`, and the sample-budget assertions.
Adding a scenario adds a case to all three; a scenario cannot exist without
being asserted, and its coverage cannot be dropped without deleting it.

The expectations live beside the scenarios and are written by hand. Deriving
them from this walk would make every assertion here a tautology — the
arithmetic is the thing under test.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.cards import (
    AnchorOpenings,
    SetAsideState,
    card_funding,
    card_position,
    card_reserve,
    ride_is_exclusive,
    set_aside_state,
)
from igab.domain.carryover import sum_through
from igab.sample_budget.card_scenarios import (
    ALL_SCENARIOS,
    ANCHORED_SCENARIOS,
    CardScenario,
    merge_into,
    scenarios_for,
    state,
    to_funding_inputs,
    walk,
)

ANCHOR = date(2026, 8, 15)
#: Every scenario there is — the demoed set plus the anchored-import shapes,
#: which live beside the demo rather than in it (one budget, one anchor).
EVERY = ALL_SCENARIOS + ANCHORED_SCENARIOS
IDS = [s.slug for s in EVERY]


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_the_card_lands_where_the_scenario_says(scenario: CardScenario):
    assert scenario.expect.differences(walk(scenario, ANCHOR)) == {}, scenario.story


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_the_reserve_identity_holds(scenario: CardScenario):
    """Zero for all six, including the two the check accepts by design — an
    over-reserve explained by assignments and a negative reserve explained by
    residual. That silence is why the row reads the position instead."""
    assert walk(scenario, ANCHOR).reserve_discrepancy == Decimal("0")


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_the_five_legs_reconstruct_the_reserve(scenario: CardScenario):
    inputs = to_funding_inputs(scenario, ANCHOR)
    funding = card_funding(
        inputs.assignments,
        inputs.activity,
        inputs.outflows,
        inputs.card_categories,
        openings=inputs.openings,
    )
    opening = (
        {inputs.openings.opening_month: inputs.openings.reserve_by_card[scenario.card]}
        if inputs.openings is not None
        else None
    )
    reserve = card_reserve(funding, scenario.card, inputs.payments, opening=opening)
    month = date(ANCHOR.year, ANCHOR.month, 1)
    legs = (
        sum_through(reserve.opening, month)
        + sum_through(reserve.assignments, month)
        + sum_through(reserve.reservations, month)
        - sum_through(reserve.released, month)
        - sum_through(reserve.residual, month)
        - sum_through(reserve.payments, month)
    )
    assert legs == walk(scenario, ANCHOR).set_aside


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_residual_by_pair_decomposes_the_residual_leg(scenario: CardScenario):
    """`residual_by_pair` is attribution, never arithmetic: summed across
    categories it must equal `residual_by_card` exactly, or a surface reading
    the pairs would tell a different story than the leg total."""
    inputs = to_funding_inputs(scenario, ANCHOR)
    funding = card_funding(
        inputs.assignments,
        inputs.activity,
        inputs.outflows,
        inputs.card_categories,
        openings=inputs.openings,
    )
    by_card: dict[str, Decimal] = {}
    for (_cat, card), series in funding.residual_by_pair.items():
        by_card[card] = by_card.get(card, Decimal("0")) + sum(series.values(), Decimal("0"))
    for card, series in funding.residual_by_card.items():
        assert by_card.get(card, Decimal("0")) == sum(series.values(), Decimal("0"))
    assert set(by_card) <= set(funding.residual_by_card)


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_the_scenario_is_anchor_relative(scenario: CardScenario):
    """Every date is `RelDate`, so the same story told in a different month
    lands in the same place. The sample budget always ends 'today', and a
    scenario that drifted with the calendar would make the demo unstable and
    these tests seasonal."""
    other = date(2027, 2, 3)
    assert walk(scenario, other) == walk(scenario, ANCHOR)


def test_every_scenario_is_distinct_and_named():
    slugs = [s.slug for s in EVERY]
    cards = [s.card for s in EVERY]
    assert len(set(slugs)) == len(slugs), "two scenarios share a slug"
    assert len(set(cards)) == len(cards), "two scenarios share a card name"
    for s in EVERY:
        assert s.story.strip() and s.title.strip(), f"{s.slug} has no story"


def test_the_starter_tier_is_a_subset_that_still_teaches():
    """Two demo shapes beside the household's own everyday card is enough to
    explain the model; six is the full tour.

    `paid-in-full` is full-tier only because the starter already shows a
    healthy card — the Visa, with real texture — and a second one pinned to
    the cent would be the same lesson twice."""
    starter = scenarios_for("starter")
    assert [s.slug for s in starter] == ["carrying-debt", "month-ended-short"]
    assert set(starter) <= set(scenarios_for("full")) == set(ALL_SCENARIOS)


def test_an_event_cannot_be_spelled_backwards():
    """Amounts are positive and `kind` carries the direction, so a refund
    cannot be written as a negative charge and silently mean something else."""
    from igab.sample_budget.card_scenarios import CardEvent
    from igab.sample_budget.spec import RelDate

    with pytest.raises(ValueError, match="must be positive"):
        CardEvent(RelDate(0, 1), "spend", Decimal("-5"), "Groceries")
    with pytest.raises(ValueError, match="needs category"):
        CardEvent(RelDate(0, 1), "spend", Decimal("5"))
    with pytest.raises(ValueError, match="takes no category"):
        CardEvent(RelDate(0, 25), "pay", Decimal("5"), "Groceries")


def test_every_current_month_event_precedes_any_anchor():
    """The sample budget promises to be demo-ready on ANY date, and a row
    dated after the anchor is projected rather than written.

    A current-month charge on the 12th therefore vanishes for the first eleven
    days of every month — which is not a test failure you would see, it is a
    demo that quietly shows a different card in the first third of the month.
    It cost the scenarios their positions the moment the clock rolled into a
    new month. Day 1 is on or before every anchor there is.
    """
    late = [
        (s.slug, e.kind, e.when.day)
        for s in ALL_SCENARIOS
        for e in s.events
        if e.when.months_ago == 0 and e.when.day > 1
    ]
    assert not late, f"current-month events dated after the 1st: {late}"


def test_anchored_scenarios_stay_out_of_the_demo():
    """One budget has one anchor. The anchored shapes live beside
    ALL_SCENARIOS, and `merge_into` refuses to splice one into a household —
    doing so would truncate every other scenario's history."""
    assert not set(ANCHORED_SCENARIOS) & set(ALL_SCENARIOS)
    for s in ANCHORED_SCENARIOS:
        assert s.import_anchor is not None
    from igab.sample_budget.card_scenarios import build_scenario_spec

    spec = build_scenario_spec(ALL_SCENARIOS[:1])
    with pytest.raises(ValueError, match="anchored scenarios cannot be merged"):
        merge_into(spec, ANCHORED_SCENARIOS[:1], cash_account="Checking")


def test_a_pre_anchor_charge_reserves_nothing():
    """The behaviour anchoring exists for: history before B is the seed's
    problem, not the walk's. Re-deriving it would double-count against the
    opening — `anchored-import`'s pre-anchor 300 must move no leg."""
    scenario = next(s for s in ANCHORED_SCENARIOS if s.slug == "anchored-import")
    inputs = to_funding_inputs(scenario, ANCHOR)
    funding = card_funding(
        inputs.assignments,
        inputs.activity,
        inputs.outflows,
        inputs.card_categories,
        openings=inputs.openings,
    )
    reserved = funding.reservations_by_card.get(scenario.card, {})
    assert inputs.openings is not None
    assert all(m >= inputs.openings.month for m in reserved)
    assert sum(reserved.values(), Decimal("0")) == Decimal("100")


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_the_card_is_in_the_state_the_scenario_says(scenario: CardScenario):
    """`set_aside_state` is hand-written beside the figures, and checked here
    against the real domain — the same relationship `expect` has to `walk`."""
    assert state(scenario, ANCHOR) == scenario.set_aside_state, scenario.story


def test_every_state_but_one_has_a_scenario():
    """Eight states, and a scenario for seven of them.

    `SETTLED_ELSEWHERE` is the exception, named here rather than left as a
    silent gap: it needs ONE envelope's shortfall spread over TWO cards, and a
    `CardScenario` owns exactly one card on purpose — envelopes are named
    after their card precisely so one scenario's spending cannot move
    another's position. `test_a_shared_shortfall_cannot_be_aimed_at_one_card`
    below walks that shape through `card_funding` directly.

    This test is the thing that fails when a ninth state is added with nothing
    reaching it.
    """
    declared = {s.set_aside_state for s in EVERY}
    assert declared == set(SetAsideState) - {SetAsideState.SETTLED_ELSEWHERE}


def test_imported_debt_is_not_a_month_that_ended_short():
    """The case a YNAB-imported budget hit: a card arrives owing 2,000 nobody
    reserved for, and the household pays 300 of it from cash. Set aside is
    -300 — money paid ahead of any reserve — and that is all it is.

    It read `RIDE_UNFUNDED`: the anchor's opening debt sat in the same
    `riding` series as the budget's own rides, and `ride_is_exclusive` said
    True about a card with no rides at all. The row quoted the whole 2,000
    as "spending that rode onto this card when a month ended short" beside a
    panel showing -300, and offered to fix it by funding a month that had
    never ended short — the breakdown naming no month, because there was
    none. The truthful state is `PAID_AHEAD`; the truthful remedy is to
    assign to the card, which is the only thing that retires imported debt.
    """
    anchor, later = date(2026, 6, 1), date(2026, 7, 1)
    funding = card_funding(
        assignments_by_category={},
        activity_by_category={"groceries": {later: Decimal("0")}},
        credit_outflows={"groceries": {"card-a": {later: Decimal("0")}}},
        card_categories={"card-a": "card-a payment"},
        openings=AnchorOpenings(
            month=anchor,
            available_by_category={"groceries": Decimal("0")},
            reserve_by_card={"card-a": Decimal("0")},
            uncovered_by_card={"card-a": Decimal("2000")},
        ),
    )
    reserve = card_reserve(funding, "card-a", payments={later: Decimal("300")})
    set_aside = reserve.set_aside(later)
    assert set_aside == Decimal("-300")

    own_ride = sum_through(funding.riding_by_card.get("card-a", {}), later)
    imported = sum_through(funding.imported_riding_by_card.get("card-a", {}), later)
    assert own_ride == Decimal("0")
    assert imported == Decimal("2000")
    # No pairs → nothing to be exclusive about, and it says so.
    assert ride_is_exclusive(funding.floored_by_pair, "card-a", later) is False

    state = set_aside_state(
        card_position(set_aside, Decimal("-1700")),
        residual=Decimal("0"),
        riding=own_ride,
        residual_from_ledgers=Decimal("0"),
        ride_reaches_this_card=ride_is_exclusive(funding.floored_by_pair, "card-a", later),
    )
    assert state is SetAsideState.PAID_AHEAD


def test_ride_unfunded_never_fires_on_a_positive_set_aside():
    """Riding debt on a card that is HOLDING money is Uncovered's business.

    `month-ended-short` has 60 riding and 100 set aside, and its row must not
    offer to fix a figure nobody is asking about — the remedy sentence belongs
    to a Set aside below zero that a month-end shortfall explains.
    """
    riding_and_funded = [
        s
        for s in EVERY
        if walk(s, ANCHOR).riding > Decimal("0") and (walk(s, ANCHOR).set_aside or 0) >= 0
    ]
    assert riding_and_funded, "the guard needs a card with a ride and a healthy reserve"
    for s in riding_and_funded:
        assert s.set_aside_state is not SetAsideState.RIDE_UNFUNDED, s.slug


def _two_card_shortfall(envelope_funding: str, assigned_to_a: str):
    """One envelope, two cards, one month that ends short.

    A shared tab charges 300 on card A and 60 on card B and is funded
    `envelope_funding`, so the month ends short by the difference. Both cards
    are then paid in full. `assigned_to_a` is money put on card A's own
    envelope the following month.
    """
    month, later = date(2026, 6, 1), date(2026, 7, 1)
    funding = card_funding(
        {"Shared": {month: Decimal(envelope_funding)}, "cat-a": {later: Decimal(assigned_to_a)}},
        {"Shared": {month: Decimal("-360")}},
        {"Shared": {"card-a": {month: Decimal("300")}, "card-b": {month: Decimal("60")}}},
        {"card-a": "cat-a", "card-b": "cat-b"},
    )
    return (
        funding,
        card_reserve(funding, "card-a", {month: Decimal("300")}).set_aside(later),
        card_reserve(funding, "card-b", {month: Decimal("60")}).set_aside(later),
    )


def test_a_shared_shortfall_cannot_be_aimed_at_one_card():
    """F8, as a walk: the remedy the row used to print does nothing to the
    card being read.

    `allocate_capped` hands a month's shortfall out across that month's cards
    in a fixed order, and partial funding shrinks the LAST share first. So
    money put into the envelope moves card B and leaves card A exactly where
    it was — while card A is the row saying "fund that month's envelope and
    the ride disappears".

    The three numbers below are the entire finding. Measured, not reasoned:
    the review that raised this described a figure that clears itself, and it
    does not.
    """
    # 1. Do nothing. Both cards are short, and neither clears itself.
    _, card_a, card_b = _two_card_shortfall("0", "0")
    assert (card_a, card_b) == (Decimal("-300"), Decimal("-60"))

    # 2. Fund the envelope by 60 — what the row used to advise. Card A has not
    #    moved a cent; the 60 came off card B's ride instead.
    _, card_a_funded, card_b_funded = _two_card_shortfall("60", "0")
    assert card_a_funded == card_a, "funding the envelope must not be sold as a fix for card A"
    assert card_b_funded == Decimal("0")

    # 3. Assign 60 to card A. The only action that reaches it.
    _, card_a_assigned, _ = _two_card_shortfall("0", "60")
    assert card_a_assigned == Decimal("-240")


def test_the_shared_shortfall_reads_as_settled_elsewhere():
    """The state card A lands in, and why it is not `RIDE_UNFUNDED`: the ride
    is not exclusive to the card being read, so nothing here may promise that
    funding an envelope helps. Once the shortfall IS card A's alone, the same
    predicate says so and the promise becomes true again."""
    month, later = date(2026, 6, 1), date(2026, 7, 1)
    funding, card_a, _ = _two_card_shortfall("0", "0")
    assert not ride_is_exclusive(funding.floored_by_pair, "card-a", later)
    assert (
        set_aside_state(
            card_position(card_a, Decimal("-300")),
            residual=Decimal("0"),
            riding=sum_through(funding.riding_by_card.get("card-a", {}), later),
            residual_from_ledgers=Decimal("0"),
            ride_reaches_this_card=ride_is_exclusive(funding.floored_by_pair, "card-a", later),
        )
        is SetAsideState.SETTLED_ELSEWHERE
    )
    # Funding the envelope by 60 takes card B's ride to zero, which leaves the
    # whole remaining shortfall on card A — and only then may its row say that
    # funding that month retires it.
    funding_alone, _, _ = _two_card_shortfall("60", "0")
    assert ride_is_exclusive(funding_alone.floored_by_pair, "card-a", later)
    assert month < later
