"""The Guide's card walkthrough says what the scenarios say.

The walkthrough exists so somebody new can read how a card behaves. It would
be worse than nothing if it taught arithmetic the app does not do, so the
binding test is that its last month reproduces each scenario's own hand-written
`expect` — the same declaration the served row, the pure domain and the sample
generator are all held to.
"""

import re
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


def test_a_card_that_went_overspent_shows_the_month_it_did():
    # `paid-ahead-written-off` ends well above zero, and its lesson is the
    # month it was overspent and the 1st that covered it. A walkthrough that
    # only showed the final position would hide both.
    months = EXAMPLES["paid-ahead-written-off"].months
    assert [m.set_aside for m in months] == [-150, 200, 150]


def test_the_reimbursement_crosses_zero_in_the_month_the_money_came_back():
    # The reported confusion: the figure lands at -100 but 500 came back. Both
    # have to be visible, in the right months, or the story does not parse.
    months = {m.label: m for m in EXAMPLES["reimbursed"].months}
    assert months["Last month"].set_aside == 200
    assert months["This month"].set_aside == -100


def test_last_months_overspending_is_covered_on_the_first():
    # The same settle-up a month earlier: -300 at that month's end, zero on
    # the 1st, and this month's funded spending on top.
    months = {m.label: m for m in EXAMPLES["refund-written-off"].months}
    assert months["Last month"].set_aside == -300
    assert months["This month"].set_aside == 200


def test_every_event_kind_has_a_phrase():
    """A kind added to the scenario vocabulary and not to this map takes the
    whole Guide page down with a KeyError at import — which is how
    `cash_spend` shipped: three adapters raised a named error for the kind
    they could not build, and this one raised nothing until it was called."""
    import typing

    from igab.guide.card_examples import _EVENT_PHRASES
    from igab.sample_budget.card_scenarios import EventKind

    assert set(typing.get_args(EventKind)) == set(_EVENT_PHRASES)


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.slug)
def test_the_lesson_is_three_short_beats_and_not_a_paragraph(scenario):
    """The wall of text this replaced.

    Every scenario's `story` was shown to the reader verbatim — 59 to 186
    words of prose about integrity bounds, residual legs and which shape the
    check accepts by design. It is the right note for whoever is debugging the
    model and the wrong thing entirely to hand somebody trying to understand
    their own card.

    So the budget is enforced rather than intended. Each beat is one sentence
    or two short ones: the moment one grows a clause about why the walk does
    what it does, the page is a paragraph again and nobody reads it.
    """
    lesson = scenario.lesson
    for name in ("happens", "reads", "todo"):
        text = getattr(lesson, name)
        assert text, f"{scenario.slug}: {name} is empty"
        assert "\n" not in text, f"{scenario.slug}: {name} is more than one line"
        assert len(text) <= 190, f"{scenario.slug}: {name} is {len(text)} chars, budget is 190"
        assert text[-1] in ".?", f"{scenario.slug}: {name} does not end a sentence"
        # Sentence ENDS, not periods: "$0.00" and "$1,900" carry dots that
        # are not full stops, and counting those measured the wrong thing.
        sentences = len(re.findall(r"[.?](?:\s|$)", text))
        assert sentences <= 2, f"{scenario.slug}: {name} runs to {sentences} sentences, budget is 2"


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.slug)
def test_a_situation_with_nothing_to_do_says_so_in_as_many_words(scenario):
    """ "Nothing" is an answer, and the one people most need to be given.

    Four of these situations are entirely normal — a settle-up, a credit
    balance, a dip that already recovered, a card running the loop correctly.
    A page that ends every situation with a suggestion teaches that all of
    them are problems, which is the reading this whole tab exists to undo.
    """
    quiet = {
        "paid-in-full",
        "credit-balance",
        "settled-by-others",
        "paid-ahead-written-off",
        "paid-ahead-covered",
        "refund-written-off",
        "anchored-negative-opening",
    }
    says_nothing = scenario.lesson.todo.startswith("Nothing")
    assert says_nothing == (scenario.slug in quiet), (
        f"{scenario.slug}: todo starts with 'Nothing' = {says_nothing}, "
        f"but it is {'' if scenario.slug in quiet else 'not '}a do-nothing situation"
    )


def test_the_developer_story_never_reaches_the_reader():
    """`story` and `lesson` are two descriptions of one scenario, on purpose —
    different audiences, different content. The guard is that only one of them
    is served: a served `story` is how the wall of text comes back."""
    from dataclasses import fields

    from igab.guide.card_examples import CardExample

    assert "story" not in {f.name for f in fields(CardExample)}
