"""The probe's inlined arithmetic must agree with domain/cards.py, exactly.

`scripts/card_reserve_probe.py` deliberately carries its own copy of the
reserve walk: it runs inside an arbitrary deployed IGAB container, where
importing that deployment's `domain/cards.py` would report what that version
believes rather than what the data says. The copy is allowed because it is
pinned — this suite runs both implementations over every scenario in
`sample_budget/card_scenarios.py` and requires agreement to the cent, leg by
leg. Change the walk in `domain/cards.py` and this file is what tells you the
probe has to follow.

No database: both sides are pure functions over the same plain dicts.
"""

import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from igab.domain.cards import card_funding as domain_funding
from igab.domain.cards import card_position as domain_position
from igab.domain.cards import card_reserve
from igab.domain.carryover import sum_through
from igab.sample_budget.card_scenarios import (
    ALL_SCENARIOS,
    ANCHORED_SCENARIOS,
    CardScenario,
    to_funding_inputs,
)

_PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "card_reserve_probe.py"
_spec = importlib.util.spec_from_file_location("card_reserve_probe", _PROBE_PATH)
assert _spec is not None and _spec.loader is not None
probe = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = probe  # dataclasses resolves the module through here
_spec.loader.exec_module(probe)

ANCHOR = date(2026, 8, 15)
MONTH = date(ANCHOR.year, ANCHOR.month, 1)
EVERY = ALL_SCENARIOS + ANCHORED_SCENARIOS
IDS = [s.slug for s in EVERY]


def _both(scenario: CardScenario):
    inputs = to_funding_inputs(scenario, ANCHOR)
    probe_openings = (
        probe.Openings(
            month=inputs.openings.month,
            available_by_category=dict(inputs.openings.available_by_category),
            reserve_by_card=dict(inputs.openings.reserve_by_card),
            uncovered_by_card=dict(inputs.openings.uncovered_by_card),
        )
        if inputs.openings is not None
        else None
    )
    ours = probe.card_funding(
        inputs.assignments,
        inputs.activity,
        inputs.outflows,
        inputs.card_categories,
        openings=probe_openings,
    )
    theirs = domain_funding(
        inputs.assignments,
        inputs.activity,
        inputs.outflows,
        inputs.card_categories,
        openings=inputs.openings,
    )
    return inputs, ours, theirs


def _opening_leg(inputs, card):
    if inputs.openings is None:
        return None
    return {inputs.openings.opening_month: inputs.openings.reserve_by_card[card]}


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_every_leg_series_agrees(scenario: CardScenario):
    """Month-by-month, not just in total: the timeline is built from the
    monthly series, so a compensating error would survive a totals-only
    check and put the first breach in the wrong month."""
    inputs, ours, theirs = _both(scenario)
    card = scenario.card
    reserve = card_reserve(theirs, card, inputs.payments, opening=_opening_leg(inputs, card))
    assert ours.assignments_by_card.get(card, {}) == reserve.assignments
    assert ours.reservations_by_card.get(card, {}) == reserve.reservations
    assert ours.released_by_card.get(card, {}) == reserve.released
    assert ours.residual_by_card.get(card, {}) == reserve.residual
    assert ours.riding_by_card.get(card, {}) == theirs.riding_by_card.get(card, {})
    assert ours.covered_by_card.get(card, {}) == theirs.covered_by_card.get(card, {})
    assert ours.floored_by_card.get(card, {}) == theirs.floored_by_card.get(card, {})
    assert ours.end_balances == theirs.end_balances
    assert ours.residual_by_pair == theirs.residual_by_pair


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_the_timeline_lands_on_the_domain_set_aside(scenario: CardScenario):
    inputs, ours, theirs = _both(scenario)
    card = scenario.card
    legs = {
        "opening": _opening_leg(inputs, card) or {},
        "assigned": ours.assignments_by_card.get(card, {}),
        "reserved": ours.reservations_by_card.get(card, {}),
        "released": ours.released_by_card.get(card, {}),
        "residual": ours.residual_by_card.get(card, {}),
        "payments": inputs.payments,
    }
    timeline = probe.card_timeline(legs, {}, ours.riding_by_card.get(card, {}))
    want = card_reserve(
        theirs, card, inputs.payments, opening=_opening_leg(inputs, card)
    ).set_aside(MONTH)
    got = timeline[-1].set_aside if timeline else Decimal("0")
    assert got == want, scenario.story
    if timeline:
        assert timeline[-1].riding == sum_through(theirs.riding_by_card.get(card, {}), MONTH)


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_the_position_agrees(scenario: CardScenario):
    inputs, _, theirs = _both(scenario)
    set_aside = card_reserve(
        theirs, scenario.card, inputs.payments, opening=_opening_leg(inputs, scenario.card)
    ).set_aside(MONTH)
    ours = probe.card_position(set_aside, inputs.balance)
    want = domain_position(set_aside, inputs.balance)
    assert (ours.uncovered, ours.over_reserved, ours.short_reserved, ours.card_credit) == (
        want.uncovered,
        want.over_reserved,
        want.short_reserved,
        want.card_credit,
    )


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_residual_attribution_sums_to_the_residual_leg(scenario: CardScenario):
    """The probe keeps residual per (category, card) — the one series the
    domain does not. It must be a decomposition of the leg, never a second
    opinion about its total."""
    _, ours, _ = _both(scenario)
    by_card: dict[str, Decimal] = {}
    for (_cat, card), series in ours.residual_by_pair.items():
        by_card[card] = by_card.get(card, Decimal("0")) + sum(series.values(), Decimal("0"))
    for card, series in ours.residual_by_card.items():
        assert by_card.get(card, Decimal("0")) == sum(series.values(), Decimal("0"))


def test_a_negative_reserve_scenario_reports_a_breach():
    """REIMBURSED ends at set_aside -100: the timeline must name a first
    breach month, and the breach's dominant leg must be the residual that
    caused it — the whole point of the probe."""
    scenario = next(s for s in ALL_SCENARIOS if s.slug == "reimbursed")
    inputs, ours, _ = _both(scenario)
    card = scenario.card
    legs = {
        "assigned": ours.assignments_by_card.get(card, {}),
        "reserved": ours.reservations_by_card.get(card, {}),
        "released": ours.released_by_card.get(card, {}),
        "residual": ours.residual_by_card.get(card, {}),
        "payments": inputs.payments,
    }
    timeline = probe.card_timeline(legs, {}, ours.riding_by_card.get(card, {}))
    breach = probe.first_breach(timeline)
    assert breach is not None
    leg, amount = breach.ranked_legs[0]
    assert leg == "residual"
    assert amount < Decimal("0")


@pytest.mark.parametrize("scenario", EVERY, ids=IDS)
def test_breach_and_worst_months_agree_with_domain_card_timeline(scenario: CardScenario):
    """`domain/card_timeline.py` is the in-app statement of the same analysis
    the probe carries. The two must find the same breach month and the same
    worst months, or the page and the report would tell different stories
    about one card."""
    from igab.domain.card_timeline import card_timeline as domain_timeline
    from igab.domain.card_timeline import first_breach as domain_first_breach
    from igab.domain.card_timeline import worst_months as domain_worst_months

    inputs, ours, theirs = _both(scenario)
    card = scenario.card
    probe_timeline = probe.card_timeline(
        {
            "assigned": ours.assignments_by_card.get(card, {}),
            "reserved": ours.reservations_by_card.get(card, {}),
            "released": ours.released_by_card.get(card, {}),
            "residual": ours.residual_by_card.get(card, {}),
            "payments": inputs.payments,
        },
        {},
        ours.riding_by_card.get(card, {}),
    )
    reserve = card_reserve(theirs, card, inputs.payments)
    dom_timeline = domain_timeline(reserve, {}, theirs.riding_by_card.get(card, {}))

    ours_breach = probe.first_breach(probe_timeline)
    dom_breach = domain_first_breach(dom_timeline)
    assert (ours_breach is None) == (dom_breach is None)
    if ours_breach is not None and dom_breach is not None:
        assert ours_breach.month == dom_breach.month
        assert ours_breach.set_aside_before == dom_breach.set_aside_before
        assert ours_breach.set_aside_after == dom_breach.set_aside_after

    ours_worst = [cm.month for cm in probe.worst_months(probe_timeline)]
    dom_worst = [cm.month for cm in domain_worst_months(dom_timeline)]
    assert ours_worst == dom_worst


def test_the_persisted_ccp_history_round_trips_into_the_probe():
    """The import route stores YNAB's CCP Available series inside
    `budgets.import_summary` (`YNABParityOut.ccp_available_history`), and the
    probe reads it back for its overlay. Serialization is the seam: pydantic
    turns date keys and Decimals into JSON on the way in, and the probe's
    `_ccp_history_from_summary` must recover exactly what was stored — a
    drifted month format or a float round would misplace or corrupt the
    overlay without any error."""
    from igab.api.v1.imports import YNABExportConsistencyOut, YNABParityOut

    history = {
        "sapphire visa": {
            date(2024, 1, 1): Decimal("120.50"),
            date(2024, 2, 1): Decimal("-33.10"),
        },
        "harborstone rewards": {date(2023, 11, 1): Decimal("0.00")},
    }
    parity = YNABParityOut(
        month=date(2024, 2, 1),
        ynab_ready_to_assign=Decimal("10.00"),
        expected_ready_to_assign=Decimal("10.00"),
        igab_ready_to_assign=Decimal("10.00"),
        uncovered_card_debt=Decimal("0"),
        uncategorized_net=Decimal("0"),
        matches=True,
        categories_compared=0,
        categories_differing=0,
        categories_pending=0,
        categories_unmatched=0,
        top_differences=[],
        cards_compared=2,
        cards_differing=0,
        card_differences=[],
        card_history=[],
        ccp_available_history=history,
        consistency=YNABExportConsistencyOut(
            self_consistent=True,
            carryover_rows_checked=0,
            carryover_rows_violating=0,
            activity_cells_checked=0,
            activity_cells_disagreeing=0,
        ),
    )
    summary = {"parity": parity.model_dump(mode="json")}
    assert probe._ccp_history_from_summary(summary) == history
