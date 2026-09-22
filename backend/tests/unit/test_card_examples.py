"""The Guide's card walkthrough says what the scenarios say.

The walkthrough exists so somebody new can read how a card behaves. It would
be worse than nothing if it taught arithmetic the app does not do, so the
binding test is that its last month reproduces each scenario's own hand-written
`expect` — the same declaration the served row, the pure domain and the sample
generator are all held to.
"""

from datetime import date

import pytest

from igab.guide.card_examples import INTENTS, SCENARIO_INTENTS, card_examples
from igab.sample_budget.card_scenarios import ALL_SCENARIOS

TODAY = date(2026, 9, 22)
EXAMPLES = {e.slug: e for e in card_examples(TODAY)}


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.slug)
def test_the_last_month_is_where_the_scenario_says_the_card_lands(scenario):
    example = EXAMPLES[scenario.slug]
    last = example.months[-1]
    claims = {
        "balance": last.balance,
        "set_aside": last.set_aside,
        "uncovered": last.uncovered,
        "over_reserved": last.over_reserved,
        "short_reserved": last.short_reserved,
        "card_credit": last.card_credit,
        "riding": last.riding,
    }
    for name, got in claims.items():
        want = getattr(scenario.expect, name)
        if want is None:
            continue  # the scenario declines to claim this figure
        assert got == want, f"{scenario.slug}.{name}: walkthrough {got}, scenario {want}"


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.slug)
def test_every_scenario_is_offered_to_somebody(scenario):
    # A situation nobody is shown is a situation nobody was warned about.
    intents = EXAMPLES[scenario.slug].intents
    assert intents, scenario.slug
    assert set(intents) <= set(INTENTS), scenario.slug


def test_the_intent_map_covers_the_scenarios_and_nothing_else():
    # Adding a scenario without saying who it happens to should fail here
    # rather than quietly dropping it out of every reader's view.
    assert set(SCENARIO_INTENTS) == {s.slug for s in ALL_SCENARIOS}


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.slug)
def test_months_run_forward_with_no_gaps(scenario):
    months = [m.month for m in EXAMPLES[scenario.slug].months]
    assert months == sorted(months)
    assert months[-1] == date(TODAY.year, TODAY.month, 1)
    assert len(set(months)) == len(months)


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.slug)
def test_every_event_reaches_the_reader_exactly_once(scenario):
    steps = [s for m in EXAMPLES[scenario.slug].months for s in m.steps]
    assert len(steps) == len(scenario.events)
    assert all(s.says.strip() for s in steps)


def test_a_card_that_dips_and_recovers_shows_the_dip():
    # `paid-ahead-then-caught-up` ends at zero and its whole lesson is the
    # month in the middle. A walkthrough that only showed the final position
    # would teach the opposite of what the scenario is for.
    months = EXAMPLES["paid-ahead-then-caught-up"].months
    assert any(m.set_aside < 0 for m in months), [m.set_aside for m in months]
    assert months[-1].set_aside == 0


def test_the_reimbursement_crosses_zero_in_the_month_the_money_came_back():
    # The reported confusion: the figure lands at -100 but 500 came back. Both
    # have to be visible, in the right months, or the story does not parse.
    months = {m.label: m for m in EXAMPLES["reimbursed"].months}
    assert months["Last month"].set_aside == -300
    assert months["This month"].set_aside == -100
