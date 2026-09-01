"""One definition per credit-card situation, read by the demo and the suite.

A card scenario used to be written three times: as `card_funding` dicts in
`tests/unit/test_cards.py`, as imperative factory calls in
`tests/integration/test_credit_cards.py`, and — for the single shape the
sample budget could express — as `MonthlyTxn`/`TransferSpec` in `data.py`.
The same story under three vocabularies is the duplication this repository
keeps paying for: `test_the_funded_swipe_scenario` and
`test_a_funded_swipe_moves_nothing` are one scenario, and neither of them
could be shown to anybody.

Here instead: the events, and what the card must read once they have all
happened. Three adapters project that onto the three layers, so a scenario is
demoed and pinned from one place, and a card behaviour nobody put here is a
behaviour nobody demoed.

**`expect` is written by hand, never derived.** Deriving it from the walk
would make every assertion a tautology — the arithmetic is the thing under
test. The numbers below are chosen round so a reader can check them without
running anything.

Not `shared/*.json` (what `split_cases.json` does): that pattern exists for
duplication *across languages*, and every consumer of these is Python.

Amounts and card names are invented and rescaled — see the personal-data rule
in CLAUDE.md. The ratios are what teach; the digits are nobody's.
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Literal

from igab.sample_budget.spec import (
    BOTH_TIERS,
    AccountSpec,
    CategorySpec,
    ExplicitAssignment,
    OneOffTransfer,
    OneOffTxn,
    RelDate,
    SampleBudgetSpec,
    shift_months,
)

ZERO = Decimal("0")

#: What a scenario does to a card. Positive amounts throughout — `kind`
#: carries the direction, so no scenario can accidentally spell a refund as a
#: negative charge.
#:
#: spend   an outflow on the card, filed to `category`
#: refund  an inflow on the card, filed to `category`
#: pay     a transfer from the budget's cash to the card (the only kind that
#:         spends the card's reserve)
#: deposit a plain inflow on the card, filed nowhere — somebody else paid it
#: fund    an assignment to a spending category
#: assign  an assignment to this card's own payment envelope
EventKind = Literal["spend", "refund", "pay", "deposit", "fund", "assign"]

_CARD_ROWS: frozenset[str] = frozenset({"spend", "refund", "pay", "deposit"})
_NEEDS_CATEGORY: frozenset[str] = frozenset({"spend", "refund", "fund"})


@dataclass(frozen=True)
class CardEvent:
    when: RelDate
    kind: EventKind
    amount: Decimal
    category: str | None = None

    def __post_init__(self) -> None:
        if self.amount <= ZERO:
            raise ValueError(f"{self.kind} amount must be positive, got {self.amount}")
        if (self.category is None) is (self.kind in _NEEDS_CATEGORY):
            raise ValueError(
                f"{self.kind} {'needs' if self.category is None else 'takes no'} category"
            )

    def month(self, anchor: date) -> date:
        """The first of the month this event falls in."""
        year, month = shift_months(anchor, self.when.months_ago)
        return date(year, month, 1)

    def signed(self) -> Decimal:
        """What this event does to the card's balance. 0 for assignments."""
        if self.kind == "spend":
            return -self.amount
        if self.kind in ("refund", "pay", "deposit"):
            return self.amount
        return ZERO


@dataclass(frozen=True)
class ExpectedPosition:
    """What the served `CardStatus` must read once the scenario has run.

    Mirrors `domain/cards.py card_position` plus the two totals the row and
    the breakdown quote, so one declaration answers every layer.

    **`None` means "this scenario does not claim a figure here."** The demo's
    everyday card carries months of ordinary texture, and its `set_aside` is
    whatever that texture adds up to — a number nobody can check on paper, and
    one that would need rewriting every time somebody adds a coffee. Its claim
    is the other five fields, all zero, which is exactly what "this card is
    healthy" means. Pinning a figure you cannot justify is worse than leaving
    it unpinned and saying so.
    """

    uncovered: Decimal
    balance: Decimal | None = None
    set_aside: Decimal | None = None
    over_reserved: Decimal = ZERO
    short_reserved: Decimal = ZERO
    card_credit: Decimal = ZERO
    riding: Decimal = ZERO
    #: 0 for every scenario here on purpose. Two of these cards are far from
    #: their balance for reasons the identity's bounds accept, and that is the
    #: point: a row keyed on this number says nothing about them.
    reserve_discrepancy: Decimal = ZERO

    def differences(self, actual: "ExpectedPosition") -> dict[str, tuple]:
        """Fields where `actual` disagrees with what this scenario claims.
        Unclaimed fields (None) are skipped, never treated as zero."""
        out: dict[str, tuple] = {}
        for field_name, want in vars(self).items():
            if want is None:
                continue
            got = getattr(actual, field_name)
            if got != want:
                out[field_name] = (want, got)
        return out


@dataclass(frozen=True)
class CardScenario:
    slug: str
    #: The lesson the row teaches, one line. Shown beside the card in docs.
    title: str
    #: Why this shape exists and what it used to get wrong. Becomes the
    #: docstring of every test generated from it.
    story: str
    card: str
    #: Pre-budget debt. Filed nowhere, so it reads as Uncovered from day one.
    opening: Decimal
    events: tuple[CardEvent, ...]
    expect: ExpectedPosition
    tiers: tuple[str, ...] = BOTH_TIERS

    @property
    def payment_category(self) -> str:
        """The card's own envelope. Named after the card, as the app does."""
        return f"{self.card} Payment"

    def categories(self) -> tuple[str, ...]:
        """Spending categories this scenario files to, in first-seen order."""
        seen: dict[str, None] = {}
        for e in self.events:
            if e.kind in ("spend", "refund", "fund") and e.category:
                seen.setdefault(e.category, None)
        return tuple(seen)


# ── The domain adapter ────────────────────────────────────────────────────────
# The pure layer. No database, no rows — the same dicts `card_funding` takes
# from the repositories, so a scenario can be checked without a session.


@dataclass(frozen=True)
class FundingInputs:
    """A scenario as `domain/cards.py` wants to see it."""

    assignments: dict[str, dict[date, Decimal]]
    activity: dict[str, dict[date, Decimal]]
    #: SIGNED net per (category, card, month) — positive is spending, and a
    #: month that nets to an inflow arrives negative, never clamped.
    outflows: dict[str, dict[str, dict[date, Decimal]]]
    card_categories: dict[str, str]
    payments: dict[date, Decimal]
    #: Plain inflows filed nowhere. Outside the walk by construction — they
    #: move the balance and explain a card credit, and nothing else.
    unclaimed: dict[date, Decimal]
    balance: Decimal


def _bump(store: dict[date, Decimal], month: date, amount: Decimal) -> None:
    store[month] = store.get(month, ZERO) + amount


def to_funding_inputs(scenario: CardScenario, anchor: date) -> FundingInputs:
    assignments: dict[str, dict[date, Decimal]] = {}
    activity: dict[str, dict[date, Decimal]] = {}
    outflows: dict[str, dict[str, dict[date, Decimal]]] = {}
    payments: dict[date, Decimal] = {}
    unclaimed: dict[date, Decimal] = {}
    card = scenario.card

    for event in scenario.events:
        month = event.month(anchor)
        category = event.category or ""
        if event.kind == "fund":
            _bump(assignments.setdefault(category, {}), month, event.amount)
        elif event.kind == "assign":
            _bump(assignments.setdefault(scenario.payment_category, {}), month, event.amount)
        elif event.kind in ("spend", "refund"):
            # A refund is the same row with the sign flipped, in both places:
            # the envelope's activity and the card's signed net outflow.
            direction = -1 if event.kind == "refund" else 1
            _bump(activity.setdefault(category, {}), month, -direction * event.amount)
            _bump(
                outflows.setdefault(category, {}).setdefault(card, {}),
                month,
                direction * event.amount,
            )
        elif event.kind == "pay":
            _bump(payments, month, event.amount)
        elif event.kind == "deposit":
            _bump(unclaimed, month, event.amount)

    balance = scenario.opening + sum((e.signed() for e in scenario.events), ZERO)
    return FundingInputs(
        assignments=assignments,
        activity=activity,
        outflows=outflows,
        card_categories={card: scenario.payment_category},
        payments=payments,
        unclaimed=unclaimed,
        balance=balance,
    )


def walk(scenario: CardScenario, anchor: date, through: date | None = None) -> ExpectedPosition:
    """Run a scenario through the real domain and report where the card lands.

    Used to CHECK `expect`, never to produce it — see the module docstring.
    """
    from igab.domain.cards import card_funding, card_position, card_reserve, reserve_discrepancy
    from igab.domain.carryover import sum_through

    inputs = to_funding_inputs(scenario, anchor)
    month = through or date(anchor.year, anchor.month, 1)
    funding = card_funding(
        inputs.assignments, inputs.activity, inputs.outflows, inputs.card_categories
    )
    reserve = card_reserve(funding, scenario.card, inputs.payments)
    set_aside = reserve.set_aside(month)
    position = card_position(set_aside, inputs.balance)
    return ExpectedPosition(
        balance=inputs.balance,
        set_aside=set_aside,
        uncovered=position.uncovered,
        over_reserved=position.over_reserved,
        short_reserved=position.short_reserved,
        card_credit=position.card_credit,
        riding=sum_through(funding.riding_by_card.get(scenario.card, {}), month),
        reserve_discrepancy=reserve_discrepancy(
            set_aside,
            inputs.balance,
            sum_through(reserve.assignments, month),
            sum_through(funding.covered_by_card.get(scenario.card, {}), month),
            sum_through(reserve.payments, month),
            sum_through(reserve.residual, month),
            sum_through(inputs.unclaimed, month),
        ),
    )


# ── The scenarios ─────────────────────────────────────────────────────────────
# Three months each, ending in the anchor's own month. Every figure is round
# so the expectation below it can be checked by hand.


def _spend(months_ago: int, amount: str, category: str, day: int = 12) -> CardEvent:
    return CardEvent(RelDate(months_ago, day), "spend", Decimal(amount), category)


def _fund(months_ago: int, amount: str, category: str) -> CardEvent:
    return CardEvent(RelDate(months_ago, 1), "fund", Decimal(amount), category)


def _assign(months_ago: int, amount: str) -> CardEvent:
    return CardEvent(RelDate(months_ago, 1), "assign", Decimal(amount))


def _pay(months_ago: int, amount: str, day: int = 25) -> CardEvent:
    return CardEvent(RelDate(months_ago, day), "pay", Decimal(amount))


def _refund(months_ago: int, amount: str, category: str, day: int = 18) -> CardEvent:
    return CardEvent(RelDate(months_ago, day), "refund", Decimal(amount), category)


def _d(value: str) -> Decimal:
    return Decimal(value)


PAID_IN_FULL = CardScenario(
    slug="paid-in-full",
    title="Funded spending, paid every month",
    story=(
        "The shape everything else is a departure from. Every charge comes out "
        "of an envelope that had the money, so the cash it gave up moves into "
        "the card's reserve and waits there for the bill. The reserve equals "
        "what the card owes, Uncovered is nothing, and the only reason the "
        "figure is not zero is that this month's statement has not been paid "
        "yet — which is a due date, not a problem."
    ),
    card="Sapphire Visa",
    opening=_d("0"),
    events=(
        _fund(2, "200", "Groceries"),
        _spend(2, "200", "Groceries"),
        _pay(2, "200"),
        _fund(1, "200", "Groceries"),
        _spend(1, "200", "Groceries"),
        _pay(1, "200"),
        _fund(0, "200", "Groceries"),
        _spend(0, "200", "Groceries"),
    ),
    expect=ExpectedPosition(
        balance=_d("-200"),
        set_aside=_d("200"),
        uncovered=_d("0"),
    ),
)

CARRYING_DEBT = CardScenario(
    slug="carrying-debt",
    title="Old debt, paid down by assigning to the card",
    story=(
        "The card arrived with a balance the budget never funded, so it reads "
        "as Uncovered from the first day and charges nothing to Ready to "
        "Assign. New spending is funded normally; the debt comes down because "
        "money is assigned to the card each month and then paid. Uncovered "
        "falls, month by month, and nothing about it is an alarm."
    ),
    card="Harborstone Card",
    opening=_d("-3000"),
    events=(
        _fund(2, "100", "Groceries"),
        _spend(2, "100", "Groceries"),
        _assign(2, "250"),
        _pay(2, "350"),
        _fund(1, "100", "Groceries"),
        _spend(1, "100", "Groceries"),
        _assign(1, "250"),
        _pay(1, "350"),
        _fund(0, "100", "Groceries"),
        _spend(0, "100", "Groceries"),
        _assign(0, "250"),
    ),
    expect=ExpectedPosition(
        balance=_d("-2600"),
        set_aside=_d("350"),
        uncovered=_d("2250"),
    ),
)

MONTH_ENDED_SHORT = CardScenario(
    slug="month-ended-short",
    title="A late charge the envelope could not cover",
    story=(
        "Dining Out was funded 40 and a 100 dinner landed on the 28th. At the "
        "month end the 60 it could not cover rode onto the card, permanently: "
        "funding Dining Out the FOLLOWING month does not reach back, and only "
        "raising that month's assignment retires it. This is the shape a due "
        "date crossing a month boundary produces, and the one people mistake "
        "for the statement lag — which costs nothing."
    ),
    card="Meridian Card",
    opening=_d("0"),
    events=(
        _fund(2, "40", "Dining Out"),
        _spend(2, "100", "Dining Out", day=28),
        _fund(1, "80", "Dining Out"),
        _spend(1, "80", "Dining Out"),
        _pay(1, "100"),
        _fund(0, "80", "Dining Out"),
        _spend(0, "80", "Dining Out"),
    ),
    expect=ExpectedPosition(
        balance=_d("-160"),
        set_aside=_d("100"),
        uncovered=_d("60"),
        riding=_d("60"),
    ),
)

OVER_RESERVED = CardScenario(
    slug="over-reserved",
    title="Assignments with no debt to retire, accumulating",
    story=(
        "A card paid from funded envelopes never has riding debt for an "
        "assignment to retire, so every dollar assigned to it stays in the "
        "envelope — for the life of the budget. The reserve settles at what "
        "was assigned, not at what the card owes, and the surplus is safe to "
        "release. The integrity check is silent here on purpose: an "
        "over-reserve explained by assignments IS explained, which is why the "
        "row reads the position instead of waiting for the check."
    ),
    card="Summit Rewards",
    opening=_d("0"),
    events=(
        _fund(2, "50", "Streaming"),
        _spend(2, "50", "Streaming"),
        _assign(2, "400"),
        _pay(2, "50"),
        _fund(1, "50", "Streaming"),
        _spend(1, "50", "Streaming"),
        _assign(1, "400"),
        _pay(1, "50"),
        _fund(0, "50", "Streaming"),
        _spend(0, "50", "Streaming"),
        _assign(0, "400"),
    ),
    expect=ExpectedPosition(
        balance=_d("-50"),
        set_aside=_d("1250"),
        uncovered=_d("0"),
        over_reserved=_d("1200"),
    ),
    tiers=("full",),
)

REIMBURSED = CardScenario(
    slug="reimbursed",
    title="Somebody else paid part of the bill",
    story=(
        "A share of the bill is settled by someone else and filed to the "
        "category that tracks what they owe. That category never charged this "
        "card, so there is nothing to hand back to it: the money reduces the "
        "reserve without releasing any envelope's cash, uncapped, and the "
        "reserve goes below zero while the card still owes thousands. Not an "
        "overpayment — the card holds none of your money — and the second "
        "shape the integrity check accepts by design."
    ),
    card="Alder Grove Card",
    opening=_d("-2000"),
    events=(
        _fund(2, "200", "Groceries"),
        _spend(2, "200", "Groceries"),
        _pay(2, "200"),
        _fund(1, "200", "Groceries"),
        _spend(1, "200", "Groceries"),
        _refund(1, "500", "Shared Expenses"),
        _fund(0, "200", "Groceries"),
        _spend(0, "200", "Groceries"),
    ),
    expect=ExpectedPosition(
        balance=_d("-1900"),
        set_aside=_d("-100"),
        uncovered=_d("1900"),
        short_reserved=_d("100"),
    ),
    tiers=("full",),
)

CREDIT_BALANCE = CardScenario(
    slug="credit-balance",
    title="Genuinely overpaid — the card holds your money",
    story=(
        "Paid far more than was ever charged, so the card owes nothing and "
        "then some. This is the only state the word 'overpaid' was ever true "
        "of, and until this list existed it was the sample budget's only card "
        "shape — the first thing a new user saw was a card that owed them "
        "thousands, with nothing saying why."
    ),
    card="Nordvik Store Card",
    opening=_d("0"),
    events=(
        _fund(2, "60", "Shopping"),
        _spend(2, "60", "Shopping"),
        _pay(2, "200"),
        _fund(1, "60", "Shopping"),
        _spend(1, "60", "Shopping"),
        _pay(1, "200"),
        _fund(0, "60", "Shopping"),
        _spend(0, "60", "Shopping"),
    ),
    expect=ExpectedPosition(
        balance=_d("220"),
        set_aside=_d("-220"),
        uncovered=_d("0"),
        short_reserved=_d("220"),
        card_credit=_d("220"),
    ),
    tiers=("full",),
)

#: Order is the order the demo shows them: the healthy card first, so the
#: strip does not open on an oddity the way it used to.
ALL_SCENARIOS: tuple[CardScenario, ...] = (
    PAID_IN_FULL,
    CARRYING_DEBT,
    MONTH_ENDED_SHORT,
    OVER_RESERVED,
    REIMBURSED,
    CREDIT_BALANCE,
)


def scenarios_for(tier: str) -> tuple[CardScenario, ...]:
    return tuple(s for s in ALL_SCENARIOS if tier in s.tiers)


# ── The generator adapter ─────────────────────────────────────────────────────
# The third projection: a scenario as sample-budget spec elements, so the demo
# shows the same six shapes the suites assert.


@dataclass(frozen=True)
class SpecElements:
    account: AccountSpec
    payment_category: CategorySpec
    one_offs: tuple[OneOffTxn, ...]
    transfers: tuple[OneOffTransfer, ...]
    assignments: tuple[ExplicitAssignment, ...]
    #: Spending categories the scenario files to. The caller places them —
    #: they are ordinary envelopes and mostly already exist in the demo.
    spending_categories: tuple[str, ...]


def to_spec_elements(
    scenario: CardScenario, *, cash_account: str, sort_order: int = 0
) -> SpecElements:
    """A scenario as spec elements. Dates stay `RelDate`, so the demo built
    from these ends today and the assertions do not go stale in November."""
    one_offs: list[OneOffTxn] = []
    transfers: list[OneOffTransfer] = []
    assignments: list[ExplicitAssignment] = []

    if scenario.opening:
        one_offs.append(
            OneOffTxn(
                when=RelDate(scenario.events[0].when.months_ago, 1),
                account=scenario.card,
                payee="Starting Balance",
                amount=scenario.opening,
                # Filed nowhere: on a card the opening gap is debt the budget
                # never funded, not income to assign.
                category=None,
                memo="Starting balance",
                tiers=scenario.tiers,
            )
        )

    for event in scenario.events:
        if event.kind in ("spend", "refund", "deposit"):
            one_offs.append(
                OneOffTxn(
                    when=event.when,
                    account=scenario.card,
                    payee=_payee_for(event, scenario),
                    amount=event.signed(),
                    category=event.category,
                    tiers=scenario.tiers,
                )
            )
        elif event.kind == "pay":
            transfers.append(
                OneOffTransfer(
                    when=event.when,
                    from_account=cash_account,
                    to_account=scenario.card,
                    amount=event.amount,
                    memo="Card payment",
                    tiers=scenario.tiers,
                )
            )
        elif event.kind in ("fund", "assign"):
            assignments.append(
                ExplicitAssignment(
                    category=(
                        scenario.payment_category
                        if event.kind == "assign"
                        else event.category or ""
                    ),
                    when=RelDate(event.when.months_ago, 1),
                    amount=event.amount,
                    tiers=scenario.tiers,
                )
            )

    return SpecElements(
        account=AccountSpec(
            scenario.card,
            "credit_card",
            sort_order=sort_order,
            tiers=scenario.tiers,
        ),
        payment_category=CategorySpec(
            scenario.payment_category,
            linked_account=scenario.card,
            tiers=scenario.tiers,
        ),
        one_offs=tuple(one_offs),
        transfers=tuple(transfers),
        assignments=tuple(assignments),
        spending_categories=scenario.categories(),
    )


#: A payee per kind, so the register reads like a register rather than a
#: table of amounts. Deliberately generic chains — a merchant name identifies
#: nobody, unlike an employer or a servicer.
_PAYEES = {
    "spend": "Corner Market",
    "refund": "Shared Expenses Settle-Up",
    "deposit": "Payment Received",
}


def _payee_for(event: CardEvent, scenario: CardScenario) -> str:
    if event.kind == "spend" and event.category:
        return {"Dining Out": "Thai Garden", "Streaming": "Netflix", "Shopping": "Amazon"}.get(
            event.category, _PAYEES["spend"]
        )
    return _PAYEES.get(event.kind, "Corner Market")


def build_scenario_spec(
    scenarios: tuple[CardScenario, ...],
    *,
    cash_account: str = "Checking",
    monthly_income: Decimal = Decimal("6000"),
    months: int = 3,
) -> "SampleBudgetSpec":
    """A whole sample budget that is nothing but these card shapes.

    The demo mixes them into a household; this builds the minimum around them
    so a scenario can be generated and read on its own. Used by the
    sample-budget suite and by `--scenario` reproductions, where a budget with
    one card and no distractions is the point.
    """
    from igab.sample_budget.spec import (
        GroupSpec,
        MonthlyTxn,
        PayeeSpec,
        SampleBudgetSpec,
        TargetSpec,
    )

    # Tier tags are how the DEMO chooses which shapes to show. A spec built
    # for a given set of scenarios is already the choice, so they all belong
    # in it — otherwise a full-tier card generated on its own would filter
    # itself out and leave its payment pointing at an account that is not
    # there.
    scenarios = tuple(replace(s, tiers=BOTH_TIERS) for s in scenarios)
    elements = [
        to_spec_elements(s, cash_account=cash_account, sort_order=i + 1)
        for i, s in enumerate(scenarios)
    ]
    spending = tuple(dict.fromkeys(c for e in elements for c in e.spending_categories))
    payees = tuple(
        dict.fromkeys(
            [_PAYEES[k] for k in _PAYEES]
            + [
                "Starting Balance",
                "Employer Payroll",
                "Thai Garden",
                "Netflix",
                "Amazon",
            ]
        )
    )

    return SampleBudgetSpec(
        accounts=(
            AccountSpec(cash_account, "checking", sort_order=0),
            *(e.account for e in elements),
        ),
        groups=(
            GroupSpec("Income", (CategorySpec("Other Income"),), is_system=True),
            GroupSpec(
                "Everyday",
                (
                    *(CategorySpec(name, assignments_are_explicit=True) for name in spending),
                    # Somewhere for the surplus to land. Every spec needs one,
                    # or the sweep has nothing to sweep into and generation
                    # raises rather than quietly missing its target.
                    CategorySpec(
                        "Savings",
                        sweep_remainder=True,
                        target=TargetSpec("savings_balance", Decimal("1000")),
                    ),
                ),
            ),
            GroupSpec("Debt", tuple(e.payment_category for e in elements)),
        ),
        payees=tuple(PayeeSpec(p) for p in payees),
        monthly=(
            MonthlyTxn(cash_account, "Employer Payroll", "Other Income", 1, (monthly_income,)),
        ),
        weekly=(),
        one_offs=tuple(o for e in elements for o in e.one_offs),
        transfers=(),
        scheduled=(),
        one_off_transfers=tuple(t for e in elements for t in e.transfers),
        explicit_assignments=tuple(a for e in elements for a in e.assignments),
        card_scenarios=scenarios,
        months_of_history=months,
        tba_target=Decimal("150"),
    )
