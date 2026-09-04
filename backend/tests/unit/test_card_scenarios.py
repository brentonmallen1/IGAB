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

from igab.domain.cards import card_funding, card_reserve
from igab.domain.carryover import sum_through
from igab.sample_budget.card_scenarios import (
    ALL_SCENARIOS,
    ANCHORED_SCENARIOS,
    CardScenario,
    merge_into,
    scenarios_for,
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
