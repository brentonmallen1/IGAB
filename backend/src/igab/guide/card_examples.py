"""The Guide's credit-card walkthrough, month by month.

Every figure here is produced by `card_scenarios.walk` — the same domain the
budget page serves from — so the Guide cannot teach arithmetic the app does not
do. CLAUDE.md keeps card situations in exactly one home
(`sample_budget/card_scenarios.py`); this reads that home and shapes it for a
reader, and adds no card rule of its own.

The one thing written here is the reader's-eye framing: which month a step
belongs to, what the step did in plain words, and which way of using a card
each scenario speaks to. Amounts, positions and the wording all come from
the scenario.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from igab.sample_budget.card_scenarios import (
    ALL_SCENARIOS,
    CardEvent,
    CardScenario,
    walk,
)
from igab.sample_budget.spec import shift_months

ZERO = Decimal("0")

#: How someone is using the card. A scenario can speak to more than one — the
#: reader picks the way they actually run their card and sees only what can
#: happen to them.
#:
#: in-full      paid off every month
#: paying-down  carrying a balance and assigning to the card to clear it
#: carrying     carrying a balance without paying extra at the moment
INTENTS: dict[str, tuple[str, str]] = {
    "in-full": (
        "I pay it off every month",
        "The card is a convenience, not a loan. Every charge comes out of an "
        "envelope that had the money, so Set aside should track what the card "
        "owes and Uncovered should sit at nothing.",
    ),
    "paying-down": (
        "I'm paying a balance down",
        "There is old debt the budget never funded. It shows as Uncovered and "
        "charges nothing; it comes down because you assign to the card each "
        "month and then pay. Set aside will sit far below the balance, and "
        "that is right.",
    ),
    "carrying": (
        "I'm carrying a balance for now",
        "New spending is funded normally and the old balance waits. Uncovered "
        "stands still, which is information rather than an alarm — nothing "
        "leaves your budget until you choose to assign money to the card.",
    ),
}

#: Which ways of using a card each scenario can happen to. Hand-assigned: a
#: scenario is a situation, and situations do not derive their own audience.
SCENARIO_INTENTS: dict[str, tuple[str, ...]] = {
    "paid-in-full": ("in-full",),
    "carrying-debt": ("paying-down",),
    "month-ended-short": ("in-full", "paying-down", "carrying"),
    "over-reserved": ("in-full",),
    "reimbursed": ("in-full", "paying-down", "carrying"),
    "unfiled-spending": ("in-full", "paying-down", "carrying"),
    "unlinked-payment": ("in-full", "paying-down", "carrying"),
    "paid-ahead-then-caught-up": ("paying-down", "carrying"),
    "credit-balance": ("in-full",),
    "settled-by-others": ("in-full", "paying-down", "carrying"),
    "ride-unfunded": ("in-full", "paying-down", "carrying"),
    "paid-ahead": ("paying-down", "carrying"),
}

#: What each event did, for a reader. `{amount}` and `{category}` are filled.
_EVENT_PHRASES: dict[str, str] = {
    "fund": "Budget {amount} into {category}",
    "spend": "Spend {amount} on the card, from {category}",
    "cash_spend": "Spend {amount} out of checking, from {category}",
    "charge": "Spend {amount} on the card and file it nowhere",
    "refund": "{amount} comes back onto the card, filed to {category}",
    "pay": "Pay the card {amount} by transfer from checking",
    "deposit": "{amount} lands on the card from somewhere else",
    "assign": "Assign {amount} to the card",
}


def _money(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def _phrase(event: CardEvent) -> str:
    return _EVENT_PHRASES[event.kind].format(
        amount=_money(event.amount), category=event.category or ""
    )


def _month_label(months_ago: int) -> str:
    if months_ago == 0:
        return "This month"
    if months_ago == 1:
        return "Last month"
    return f"{months_ago} months ago"


@dataclass(frozen=True)
class CardExampleStep:
    """One event, and what the card reads once it has happened.

    The position is the card's position at the END of the step's month, not
    after this single event — `walk` answers per month, which is the grain the
    served row answers at too. Steps inside a month therefore share a
    position, and the phrasing says what each one did.
    """

    kind: str
    amount: Decimal
    category: str | None
    day: int
    says: str


@dataclass(frozen=True)
class CardExampleMonth:
    month: date
    label: str
    steps: list[CardExampleStep]
    set_aside: Decimal
    balance: Decimal
    uncovered: Decimal
    over_reserved: Decimal
    short_reserved: Decimal
    card_credit: Decimal
    riding: Decimal


@dataclass(frozen=True)
class CardExample:
    slug: str
    title: str
    #: The situation in three beats (`CardScenario.lesson`). `story` is NOT
    #: served: it is the scenario's own note about why the shape exists and
    #: what it used to get wrong, written for whoever is debugging the model,
    #: and it ran to 186 words of prose about integrity bounds and residual
    #: legs. A paragraph of that is not something to ask a reader for.
    happens: str
    reads: str
    todo: str
    card: str
    intents: list[str]
    opening: Decimal
    months: list[CardExampleMonth] = field(default_factory=list)


def _months_of(scenario: CardScenario, today: date) -> list[tuple[int, date]]:
    """Every month the scenario touches, earliest first, none skipped.

    A month with no events still gets a row: the reserve can move across a
    boundary without anybody doing anything, which is most of what
    `month-ended-short` is about.
    """
    earliest = max((e.when.months_ago for e in scenario.events), default=0)
    out = []
    for ago in range(earliest, -1, -1):
        year, month_no = shift_months(today, ago)
        out.append((ago, date(year, month_no, 1)))
    return out


def card_examples(today: date) -> list[CardExample]:
    """Every card scenario, walked month by month for a reader."""
    return [_example(s, today) for s in ALL_SCENARIOS]


def _example(scenario: CardScenario, today: date) -> CardExample:
    months = []
    for ago, month in _months_of(scenario, today):
        position = walk(scenario, today, through=month)
        events = sorted(
            (e for e in scenario.events if e.month(today) == month),
            key=lambda e: e.when.day or 1,
        )
        months.append(
            CardExampleMonth(
                month=month,
                label=_month_label(ago),
                steps=[
                    CardExampleStep(
                        kind=e.kind,
                        amount=e.amount,
                        category=e.category,
                        day=e.when.day or 1,
                        says=_phrase(e),
                    )
                    for e in events
                ],
                # `walk` leaves a figure None only where a scenario declines to
                # claim it; the walk itself always produces one.
                set_aside=position.set_aside if position.set_aside is not None else ZERO,
                balance=position.balance if position.balance is not None else ZERO,
                uncovered=position.uncovered,
                over_reserved=position.over_reserved,
                short_reserved=position.short_reserved,
                card_credit=position.card_credit,
                riding=position.riding,
            )
        )
    return CardExample(
        slug=scenario.slug,
        title=scenario.title,
        happens=scenario.lesson.happens,
        reads=scenario.lesson.reads,
        todo=scenario.lesson.todo,
        card=scenario.card,
        intents=list(SCENARIO_INTENTS[scenario.slug]),
        opening=scenario.opening,
        months=months,
    )
