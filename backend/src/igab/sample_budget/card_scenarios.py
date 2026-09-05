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

from igab.domain.cards import AnchorOpenings
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
#: charge  an outflow on the card, filed NOWHERE — the emergency expense the
#:         user never categorised. Symmetric with `deposit`, and invisible to
#:         the reserve for the same reason: exposure is per (category, card),
#:         so a row with no category never reserves, never rides, and never
#:         releases. It moves the balance and nothing else, which is why the
#:         whole of it reads as uncovered.
#: refund  an inflow on the card, filed to `category`
#: pay     a transfer from the budget's cash to the card (the only kind that
#:         spends the card's reserve)
#: deposit a plain inflow on the card, filed nowhere — somebody else paid it,
#:         or a payment the importer never paired to its cash leg
#: fund    an assignment to a spending category
#: assign  an assignment to this card's own payment envelope
EventKind = Literal["spend", "charge", "refund", "pay", "deposit", "fund", "assign"]

_CARD_ROWS: frozenset[str] = frozenset({"spend", "charge", "refund", "pay", "deposit"})
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
        if self.kind in ("spend", "charge"):
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
    #: The anchor month off the card's own ledger — the four figures the
    #: breakdown's "This month" block quotes. Hand-written like everything
    #: else here; an inflow is what this model has been bitten by twice, and
    #: before these fields existed the month arithmetic was asserted nowhere
    #: in the suite. `debt_change_this_month` is signed, positive = shrank;
    #: the other three are magnitudes, and the identity the panel renders is
    #: inflows − charged == debt_change.
    charged_this_month: Decimal | None = None
    inflows_this_month: Decimal | None = None
    paid_this_month: Decimal | None = None
    debt_change_this_month: Decimal | None = None

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
class CardAnchor:
    """An import anchor, scenario-shaped: the position the budget starts from.

    Budget-level metadata, not a register event — which is why it is a field
    on the scenario rather than an `EventKind`: it writes no row, has no
    payee, and dates itself. `months_ago` is B (the first re-derived month)
    relative to today; the openings are stated at B−1, exactly as the
    importer writes them (db.models.ImportAnchor). Events before B still
    build register rows and balances — the production shape: register full,
    walk truncated.
    """

    #: B, as months before today. Openings are dated one month earlier.
    months_ago: int
    #: The card's opening reserve (YNAB's CCP Available at B−1). Signed.
    reserve: Decimal
    #: Debt no reserve stood behind at B−1 — rides under ANCHOR_OPENING.
    uncovered: Decimal
    #: Per spending-category openings (YNAB's Available at B−1), sparse.
    available: tuple[tuple[str, Decimal], ...] = ()


@dataclass(frozen=True)
class CardScenario:
    slug: str
    #: The lesson the row teaches, one line. Shown beside the card in docs.
    title: str
    #: Why this shape exists and what it used to get wrong. Becomes the
    #: docstring of every test generated from it.
    story: str
    card: str
    #: The card's name in its category names — "Harborstone Groceries". Card
    #: names are unique budget-wide, and so are category names, so scenario
    #: envelopes cannot be shared and must not look like they are. A shared
    #: envelope is not a cosmetic problem: a shortfall rides from whichever
    #: card carried it, so one scenario's spending moves another's position.
    short: str
    #: Pre-budget debt. Filed nowhere, so it reads as Uncovered from day one.
    opening: Decimal
    events: tuple[CardEvent, ...]
    expect: ExpectedPosition
    tiers: tuple[str, ...] = BOTH_TIERS
    #: Set only on ANCHORED_SCENARIOS — never in the demo (`merge_into`
    #: refuses them: one budget has one anchor, and splicing one in would
    #: truncate every other scenario's history).
    import_anchor: CardAnchor | None = None

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
    #: The import anchor as `card_funding` wants it, or None. Built from
    #: `CardScenario.import_anchor` — the same shape the serving side builds
    #: from `ImportAnchor` rows, so the scenario checker and production walk
    #: the identical seeds.
    openings: "AnchorOpenings[str, str] | None" = None
    #: `max(0, card balance at end of B−1)` — the T3 allowance for a card
    #: imported in credit, mirrored from pre-anchor events the way the
    #: serving side reads it live from the register.
    opening_credit: Decimal = ZERO


def _bump(store: dict[date, Decimal], month: date, amount: Decimal) -> None:
    store[month] = store.get(month, ZERO) + amount


def to_funding_inputs(scenario: CardScenario, today: date) -> FundingInputs:
    assignments: dict[str, dict[date, Decimal]] = {}
    activity: dict[str, dict[date, Decimal]] = {}
    outflows: dict[str, dict[str, dict[date, Decimal]]] = {}
    payments: dict[date, Decimal] = {}
    unclaimed: dict[date, Decimal] = {}
    card = scenario.card

    for event in scenario.events:
        month = event.month(today)
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
        elif event.kind == "charge":
            # Deliberately contributes to NOTHING here. Exposure is per
            # (category, card), so a row filed nowhere never reserves, never
            # rides and can never be released — it reaches the card only
            # through `signed()` in the balance below. That is the behaviour
            # under test, and stating it as a branch keeps it from reading as
            # an omission.
            pass
        elif event.kind == "pay":
            _bump(payments, month, event.amount)
        elif event.kind == "deposit":
            _bump(unclaimed, month, event.amount)
        else:  # pragma: no cover - the guard is the point
            raise AssertionError(f"to_funding_inputs cannot walk a {event.kind!r} event")

    balance = scenario.opening + sum((e.signed() for e in scenario.events), ZERO)
    openings = None
    opening_credit = ZERO
    if scenario.import_anchor is not None:
        ia = scenario.import_anchor
        year, month_no = shift_months(today, ia.months_ago)
        boundary = date(year, month_no, 1)
        openings = AnchorOpenings(
            month=boundary,
            available_by_category=dict(ia.available),
            reserve_by_card={card: ia.reserve},
            uncovered_by_card={card: ia.uncovered},
        )
        pre_anchor = scenario.opening + sum(
            (e.signed() for e in scenario.events if e.month(today) < boundary), ZERO
        )
        opening_credit = max(ZERO, pre_anchor)
        # The two reserve legs the domain walk never sees are truncated at B,
        # exactly as `BudgetService.card_walk` truncates its repository sums —
        # the seed at B−1 already accounts for everything earlier. The
        # BALANCE keeps every event: register full, walk truncated.
        payments = {m: v for m, v in payments.items() if m >= boundary}
        unclaimed = {m: v for m, v in unclaimed.items() if m >= boundary}
    return FundingInputs(
        assignments=assignments,
        activity=activity,
        outflows=outflows,
        card_categories={card: scenario.payment_category},
        payments=payments,
        unclaimed=unclaimed,
        balance=balance,
        openings=openings,
        opening_credit=opening_credit,
    )


def walk(scenario: CardScenario, today: date, through: date | None = None) -> ExpectedPosition:
    """Run a scenario through the real domain and report where the card lands.

    Used to CHECK `expect`, never to produce it — see the module docstring.
    """
    from igab.domain.cards import card_funding, card_position, card_reserve, reserve_discrepancy
    from igab.domain.carryover import sum_through

    inputs = to_funding_inputs(scenario, today)
    month = through or date(today.year, today.month, 1)
    funding = card_funding(
        inputs.assignments,
        inputs.activity,
        inputs.outflows,
        inputs.card_categories,
        openings=inputs.openings,
    )
    opening_leg = (
        {inputs.openings.opening_month: inputs.openings.reserve_by_card[scenario.card]}
        if inputs.openings is not None
        else None
    )
    reserve = card_reserve(funding, scenario.card, inputs.payments, opening=opening_leg)
    set_aside = reserve.set_aside(month)
    position = card_position(set_aside, inputs.balance)
    # The month ledger, summed straight off the events — deliberately a
    # different path from the SQL (`card_month_flows`) the served figure
    # takes, so the two check each other through the shared expectations.
    month_events = [e for e in scenario.events if e.month(today) == month]
    charged = sum((e.amount for e in month_events if e.kind in ("spend", "charge")), ZERO)
    inflows = sum((e.amount for e in month_events if e.kind in ("refund", "pay", "deposit")), ZERO)
    paid = sum((e.amount for e in month_events if e.kind == "pay"), ZERO)
    return ExpectedPosition(
        balance=inputs.balance,
        set_aside=set_aside,
        uncovered=position.uncovered,
        charged_this_month=charged,
        inflows_this_month=inflows,
        paid_this_month=paid,
        debt_change_this_month=inflows - charged,
        over_reserved=position.over_reserved,
        short_reserved=position.short_reserved,
        card_credit=position.card_credit,
        riding=sum_through(funding.riding_by_card.get(scenario.card, {}), month),
        # The serving arithmetic exactly (budget_service.get_budget_summary):
        # the opening reserve folds into `assigned`, and `opening_credit` is
        # the T3 allowance — this checker must not drift from what is served.
        reserve_discrepancy=reserve_discrepancy(
            set_aside,
            inputs.balance,
            sum_through(reserve.opening, month) + sum_through(reserve.assignments, month),
            sum_through(funding.covered_by_card.get(scenario.card, {}), month),
            sum_through(reserve.payments, month),
            sum_through(reserve.residual, month),
            sum_through(inputs.unclaimed, month),
            opening_credit=inputs.opening_credit,
        ),
    )


# ── The scenarios ─────────────────────────────────────────────────────────────
# Three months each, ending in the anchor's own month. Every figure is round
# so the expectation below it can be checked by hand.


def _spend(months_ago: int, amount: str, category: str, day: int = 12) -> CardEvent:
    """A charge. Current-month charges are dated the 1st on purpose — see
    `test_every_current_month_event_precedes_any_anchor`."""
    return CardEvent(RelDate(months_ago, day), "spend", Decimal(amount), category)


def _fund(months_ago: int, amount: str, category: str) -> CardEvent:
    return CardEvent(RelDate(months_ago, 1), "fund", Decimal(amount), category)


def _assign(months_ago: int, amount: str) -> CardEvent:
    return CardEvent(RelDate(months_ago, 1), "assign", Decimal(amount))


def _pay(months_ago: int, amount: str, day: int = 25) -> CardEvent:
    return CardEvent(RelDate(months_ago, day), "pay", Decimal(amount))


def _charge(months_ago: int, amount: str, day: int = 12) -> CardEvent:
    """An outflow filed nowhere. No category, by construction — the whole
    point of the kind."""
    return CardEvent(RelDate(months_ago, day), "charge", _d(amount))


def _deposit(months_ago: int, amount: str, day: int = 16) -> CardEvent:
    """An inflow filed nowhere: somebody else settled part of the bill, or a
    payment arrived as a plain credit because its cash leg was never paired."""
    return CardEvent(RelDate(months_ago, day), "deposit", _d(amount))


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
    card="Cedar Point Visa",
    short="Cedar Point",
    opening=_d("0"),
    # Paid a month in arrears, which is how a statement actually works — and
    # which keeps the card showing a balance in EVERY month. Paying each
    # month's charge inside that same month nets the card to zero everywhere
    # except the anchor, so the demo's healthiest card rendered as a row of
    # dashes for anyone who stepped back a month.
    events=(
        _fund(2, "200", "Cedar Point Groceries"),
        _spend(2, "200", "Cedar Point Groceries"),
        _fund(1, "200", "Cedar Point Groceries"),
        _spend(1, "200", "Cedar Point Groceries"),
        _pay(1, "200"),
        _fund(0, "200", "Cedar Point Groceries"),
        _spend(0, "200", "Cedar Point Groceries", day=1),
        _pay(0, "200", day=1),
    ),
    # Full tier only: the starter already shows a healthy card, and it shows
    # one with real texture. This is the same shape with a position pinned to
    # the cent, which is a different job.
    tiers=("full",),
    expect=ExpectedPosition(
        balance=_d("-200"),
        set_aside=_d("200"),
        uncovered=_d("0"),
        # 200 spent, the 200 payment received the same day: the debt this
        # month net-moved not at all.
        charged_this_month=_d("200"),
        inflows_this_month=_d("200"),
        paid_this_month=_d("200"),
        debt_change_this_month=_d("0"),
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
    short="Harborstone",
    opening=_d("-3000"),
    events=(
        _fund(2, "100", "Harborstone Groceries"),
        _spend(2, "100", "Harborstone Groceries"),
        _assign(2, "250"),
        _pay(2, "350"),
        _fund(1, "100", "Harborstone Groceries"),
        _spend(1, "100", "Harborstone Groceries"),
        _assign(1, "250"),
        _pay(1, "350"),
        _fund(0, "100", "Harborstone Groceries"),
        _spend(0, "100", "Harborstone Groceries", day=1),
        _assign(0, "250"),
    ),
    expect=ExpectedPosition(
        balance=_d("-2600"),
        set_aside=_d("350"),
        uncovered=_d("2250"),
        # The anchor month's payment has not gone out yet — only the spend.
        charged_this_month=_d("100"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-100"),
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
    short="Meridian",
    opening=_d("0"),
    events=(
        _fund(2, "40", "Meridian Dining Out"),
        _spend(2, "100", "Meridian Dining Out", day=28),
        _fund(1, "80", "Meridian Dining Out"),
        _spend(1, "80", "Meridian Dining Out"),
        _pay(1, "100"),
        _fund(0, "80", "Meridian Dining Out"),
        _spend(0, "80", "Meridian Dining Out", day=1),
    ),
    expect=ExpectedPosition(
        balance=_d("-160"),
        set_aside=_d("100"),
        uncovered=_d("60"),
        riding=_d("60"),
        charged_this_month=_d("80"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-80"),
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
    short="Summit",
    opening=_d("0"),
    events=(
        _fund(2, "50", "Summit Streaming"),
        _spend(2, "50", "Summit Streaming"),
        _assign(2, "400"),
        _pay(2, "50"),
        _fund(1, "50", "Summit Streaming"),
        _spend(1, "50", "Summit Streaming"),
        _assign(1, "400"),
        _pay(1, "50"),
        _fund(0, "50", "Summit Streaming"),
        _spend(0, "50", "Summit Streaming", day=1),
        _assign(0, "400"),
    ),
    expect=ExpectedPosition(
        balance=_d("-50"),
        set_aside=_d("1250"),
        uncovered=_d("0"),
        over_reserved=_d("1200"),
        charged_this_month=_d("50"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-50"),
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
    short="Alder Grove",
    opening=_d("-2000"),
    events=(
        _fund(2, "200", "Alder Grove Groceries"),
        _spend(2, "200", "Alder Grove Groceries"),
        _pay(2, "200"),
        _fund(1, "200", "Alder Grove Groceries"),
        _spend(1, "200", "Alder Grove Groceries"),
        _refund(1, "500", "Alder Grove Shared Expenses"),
        _fund(0, "200", "Alder Grove Groceries"),
        _spend(0, "200", "Alder Grove Groceries", day=1),
    ),
    expect=ExpectedPosition(
        balance=_d("-1900"),
        set_aside=_d("-100"),
        uncovered=_d("1900"),
        short_reserved=_d("100"),
        charged_this_month=_d("200"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-200"),
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
    short="Nordvik",
    opening=_d("0"),
    events=(
        _fund(2, "60", "Nordvik Shopping"),
        _spend(2, "60", "Nordvik Shopping"),
        _pay(2, "200"),
        _fund(1, "60", "Nordvik Shopping"),
        _spend(1, "60", "Nordvik Shopping"),
        _pay(1, "200"),
        _fund(0, "60", "Nordvik Shopping"),
        _spend(0, "60", "Nordvik Shopping", day=1),
    ),
    expect=ExpectedPosition(
        balance=_d("220"),
        set_aside=_d("-220"),
        uncovered=_d("0"),
        short_reserved=_d("220"),
        card_credit=_d("220"),
        charged_this_month=_d("60"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-60"),
    ),
    tiers=("full",),
)

UNFILED_SPENDING = CardScenario(
    slug="unfiled-spending",
    title="Charges nobody filed to an envelope",
    story=(
        "An urgent expense goes on the card and never gets a category — the "
        "case a budget has to allow, because the alternative is a user who "
        "cannot record what actually happened. Exposure is per (category, "
        "card), so a row filed nowhere reserves nothing, rides nothing, and "
        "releases nothing: it moves the balance and only the balance. Every "
        "cent of it therefore reads as uncovered, which is the honest answer "
        "— no envelope is standing behind this debt. The card that raised "
        "this had a whole month of them and read its entire balance as "
        "uncovered while Ready to pay sat at zero."
    ),
    card="Ironwood Card",
    short="Ironwood",
    opening=_d("0"),
    events=(
        _charge(2, "300"),
        _charge(1, "200"),
        _charge(0, "100", day=1),
    ),
    # Hand-computed, not derived: nothing funded and nothing assigned, so the
    # reserve never moves and the whole 600 owed is uncovered.
    expect=ExpectedPosition(
        balance=_d("-600"),
        set_aside=_d("0"),
        uncovered=_d("600"),
        charged_this_month=_d("100"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-100"),
    ),
    tiers=("full",),
)

UNLINKED_PAYMENT = CardScenario(
    slug="unlinked-payment",
    title="A payment that arrived as a plain credit",
    story=(
        "The bill was paid from checking, but the two legs were never linked "
        "— the importer sees a card credit and a cash debit and has no reason "
        "to know they are one movement. Only a transfer spends the reserve, "
        "so `paid to the card` stays at zero while the balance visibly falls, "
        "and the money lands in the 'other credits' term instead. The card "
        "that raised this showed 0.00 paid against thousands of debt "
        "repaid, with nothing on screen saying where the movement came from."
    ),
    card="Kestrel Card",
    short="Kestrel",
    opening=_d("0"),
    events=(
        _fund(2, "200", "Kestrel Groceries"),
        _spend(2, "200", "Kestrel Groceries"),
        _charge(1, "400"),
        _deposit(1, "300"),
        _charge(0, "100", day=1),
    ),
    # Hand-computed: 200 of funded spending reserves 200. The 500 of unfiled
    # charges and the 300 credit touch the balance only, leaving 400 owed
    # against a 200 reserve — so 200 is uncovered and nothing is over- or
    # short-reserved.
    expect=ExpectedPosition(
        balance=_d("-400"),
        set_aside=_d("200"),
        uncovered=_d("200"),
        charged_this_month=_d("100"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-100"),
    ),
    tiers=("full",),
)

PAID_AHEAD_THEN_CAUGHT_UP = CardScenario(
    slug="paid-ahead-then-caught-up",
    title="A payment ran ahead of the reserve, then the reserve caught up",
    story=(
        "The statement was paid in full — but the statement included debt "
        "carried in from before the budget, which nothing had reserved "
        "against, so the payment drove the reserve below zero. The next "
        "month's funded spending reserved as usual and pulled it back up. "
        "The final position is unremarkable, and that is the lesson: only "
        "the month-by-month timeline shows the dip, which is why a card's "
        "history is worth reading and its current figure is not the whole "
        "story."
    ),
    card="Foxglove Card",
    short="Foxglove",
    opening=_d("-300"),
    events=(
        _fund(2, "100", "Foxglove Groceries"),
        _spend(2, "100", "Foxglove Groceries"),
        _pay(2, "250"),
        _fund(1, "200", "Foxglove Groceries"),
        _spend(1, "200", "Foxglove Groceries"),
        _pay(0, "50", day=1),
    ),
    # Hand-computed. Reservations 100 + 200 = 300 against payments
    # 250 + 50 = 300, so the reserve lands at exactly zero — after reading
    # -150 at the end of the first month (100 reserved, 250 paid) and +50
    # after the second. The 300 of pre-budget debt was never categorized, so
    # every cent of what the card still owes is uncovered.
    # The anchor month holds only the 50 payment: nothing charged, the
    # payment is the card's one credit, and the debt steps -350 -> -300.
    expect=ExpectedPosition(
        balance=_d("-300"),
        set_aside=_d("0"),
        uncovered=_d("300"),
        charged_this_month=_d("0"),
        inflows_this_month=_d("50"),
        paid_this_month=_d("50"),
        debt_change_this_month=_d("50"),
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
    UNFILED_SPENDING,
    UNLINKED_PAYMENT,
    PAID_AHEAD_THEN_CAUGHT_UP,
    CREDIT_BALANCE,
)


def scenarios_for(tier: str) -> tuple[CardScenario, ...]:
    return tuple(s for s in ALL_SCENARIOS if tier in s.tiers)


ANCHORED_IMPORT = CardScenario(
    slug="anchored-import",
    title="A YNAB import that starts where YNAB left off",
    story=(
        "An imported budget's walks start from YNAB's own displayed position "
        "instead of re-deriving history: the reserve opens at the shipped CCP "
        "Available, the debt nothing stood behind rides under the anchor, and "
        "a pre-anchor charge reserves nothing at all — the seed already "
        "accounts for it. Assigning then retires the opening ride exactly as "
        "it retires any ride, and the identity closes with the opening folded "
        "into the assignment leg."
    ),
    card="Sapphire Visa",
    short="Sapphire",
    # Pre-budget debt plus a pre-anchor charge: at B−1 the card owes 550, of
    # which the anchor says 150 was reserved and 400 rode uncovered —
    # exactly the importer's max(0, -balance - ccp).
    opening=_d("-250"),
    import_anchor=CardAnchor(
        months_ago=2,
        reserve=_d("150"),
        uncovered=_d("400"),
        available=(("Sapphire Groceries", _d("40")),),
    ),
    events=(
        # B−1: real register history the walk must NOT re-derive. Had this
        # reserved, set_aside would read 450 and the scenario would fail.
        _spend(3, "300", "Sapphire Groceries"),
        # B: cover 250 of the opening ride, pay part of the statement.
        _assign(2, "250"),
        _pay(2, "150"),
        # Today: ordinary funded spending, reserving as ever.
        _fund(0, "100", "Sapphire Groceries"),
        _spend(0, "100", "Sapphire Groceries", day=1),
    ),
    tiers=("full",),
    expect=ExpectedPosition(
        # 250 opening debt + 300 pre-anchor spend − 150 paid + 100 today.
        balance=_d("-500"),
        # opening 150 + assigned 250 + reserved 100 − paid 150. The
        # pre-anchor 300 contributes nothing — that is the behaviour under
        # test.
        set_aside=_d("350"),
        # 500 owed − 350 reserved; equally, the 400 opening ride less the
        # 250 the assignment covered.
        uncovered=_d("150"),
        riding=_d("150"),
        charged_this_month=_d("100"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-100"),
        reserve_discrepancy=_d("0"),
    ),
)

ANCHORED_IN_CREDIT = CardScenario(
    slug="anchored-in-credit",
    title="A card imported already holding your money",
    story=(
        "A card can arrive from YNAB in credit — a refund landed after the "
        "last payment. No post-anchor leg explains that credit, so the "
        "identity needs the anchor-era allowance (`opening_credit` in "
        "reserve_discrepancy's T3): the card held this money before the "
        "budget's first re-derived month existed."
    ),
    card="Basalt Card",
    short="Basalt",
    opening=_d("0"),
    import_anchor=CardAnchor(months_ago=2, reserve=_d("0"), uncovered=_d("0")),
    events=(
        # Pre-anchor: a plain credit put the card in the black. Truncated
        # from the walk — only the balance remembers it.
        _deposit(3, "80"),
    ),
    tiers=("full",),
    expect=ExpectedPosition(
        balance=_d("80"),
        set_aside=_d("0"),
        uncovered=_d("0"),
        card_credit=_d("80"),
        riding=_d("0"),
        charged_this_month=_d("0"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("0"),
        reserve_discrepancy=_d("0"),
    ),
)

ANCHORED_CREDIT_SPENT_DOWN = CardScenario(
    slug="anchored-credit-spent-down",
    title="A card that arrived in credit, then got used",
    story=(
        "`ANCHORED_IN_CREDIT` leaves the card at rest, where the imported "
        "credit sits in `card_credit` and T3's anchor-era allowance covers "
        "it. This is the same card a month later, used the way any card is. "
        "An opening credit does NOT stay in `card_credit`: fund an envelope "
        "100 and spend it here and the card owes 20, not 100, because the "
        "credit absorbed the difference — so the envelope reserves 100 "
        "against a 20 debt and the position reads over-reserved by exactly "
        "the 80 the card came in with. That is T1's bound, not T3's. With "
        "the allowance on T3 alone, every anchored card that arrived in "
        "credit reported that 80 as drift from its first ordinary spend "
        "onward, and the integrity check repeated it every month."
    ),
    card="Larkspur Card",
    short="Larkspur",
    opening=_d("0"),
    import_anchor=CardAnchor(months_ago=2, reserve=_d("0"), uncovered=_d("0")),
    events=(
        # Pre-anchor: the credit the card was imported holding. Truncated from
        # the walk; only the balance and `opening_credit` remember it, and the
        # latter is read live off the register, never off the anchor rows.
        _deposit(3, "80"),
        # Post-anchor: ordinary funded spending, reserving as ever.
        _fund(1, "100", "Larkspur Everyday"),
        _spend(1, "100", "Larkspur Everyday"),
    ),
    tiers=("full",),
    expect=ExpectedPosition(
        # 80 credit − 100 charged.
        balance=_d("-20"),
        # The funded spend reserved its whole 100; nothing paid it out.
        set_aside=_d("100"),
        # Nothing owed beyond the reserve — the reserve is over it, not under.
        uncovered=_d("0"),
        # 100 reserved against 20 owed. The 80 is the imported credit,
        # converted; it is not a defect and the identity now says so.
        over_reserved=_d("80"),
        card_credit=_d("0"),
        riding=_d("0"),
        # Every event predates this month.
        charged_this_month=_d("0"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("0"),
        reserve_discrepancy=_d("0"),
    ),
)

#: Anchored shapes, beside — never inside — ALL_SCENARIOS: one budget has one
#: anchor, and splicing one into the demo would truncate every other
#: scenario's history. `merge_into` refuses them; `build_scenario_spec`
#: builds them a budget of their own.
ANCHORED_SCENARIOS: tuple[CardScenario, ...] = (
    ANCHORED_IMPORT,
    ANCHORED_IN_CREDIT,
    ANCHORED_CREDIT_SPENT_DOWN,
)


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
    #: Spending categories the scenario files to, named after the card.
    spending_categories: tuple[str, ...]
    #: Payees its rows name. A spec that omits one fails generation with a
    #: bare KeyError, so they travel with the rows that need them.
    payees: tuple[str, ...]


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
        if event.kind in ("spend", "charge", "refund", "deposit"):
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
        else:  # pragma: no cover - the guard is the point
            # The other two adapters raise on a kind they cannot express;
            # this one silently emitted nothing, which is how a new kind
            # ships demoed nowhere.
            raise AssertionError(f"to_spec_elements cannot build a {event.kind!r} event")

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
        payees=tuple(dict.fromkeys([o.payee for o in one_offs])),
    )


#: A payee per kind, so the register reads like a register rather than a
#: table of amounts. Deliberately generic chains — a merchant name identifies
#: nobody, unlike an employer or a servicer.
_PAYEES = {
    "spend": "Corner Market",
    "charge": "Urgent Care Clinic",
    "refund": "Shared Expenses Settle-Up",
    "deposit": "Payment Received",
}


def _payee_for(event: CardEvent, scenario: CardScenario) -> str:
    """A payee that suits the envelope. Matched on the category's tail, since
    the name carries the card's own prefix in front of it."""
    if event.kind == "spend" and event.category:
        for tail, payee in _BY_CATEGORY.items():
            if event.category.endswith(tail):
                return payee
        return _PAYEES["spend"]
    return _PAYEES.get(event.kind, _PAYEES["spend"])


_BY_CATEGORY = {
    "Dining Out": "Thai Garden",
    "Streaming": "Netflix",
    "Shopping": "Amazon",
    "Groceries": "Corner Market",
}


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


def merge_into(
    spec: SampleBudgetSpec,
    scenarios: tuple[CardScenario, ...],
    *,
    cash_account: str,
    group_name: str = "Card demos",
    sort_from: int = 50,
) -> SampleBudgetSpec:
    """Splice scenario cards into a household budget.

    Each scenario brings its own account, its own payment envelope and its own
    spending envelopes — named after the card, because category names are
    unique budget-wide and because a SHARED envelope is not a cosmetic problem:
    a month-end shortfall rides from whichever card carried it, so one
    scenario's spending would silently move another's position.

    Their envelopes are `assignments_are_explicit`, so the household's
    fund-what-you-spent inference leaves them alone — that inference would
    top up the very shortfall `month-ended-short` exists to show.
    """
    from igab.sample_budget.spec import GroupSpec, PayeeSpec

    anchored = [sc.slug for sc in scenarios if sc.import_anchor is not None]
    if anchored:
        # One budget has one anchor; splicing an anchored scenario into a
        # household would truncate every other scenario's history.
        raise ValueError(f"anchored scenarios cannot be merged into a demo: {anchored}")
    elements = [
        to_spec_elements(sc, cash_account=cash_account, sort_order=sort_from + i)
        for i, sc in enumerate(scenarios)
    ]
    spending = tuple(
        dict.fromkeys(
            (name, sc.tiers)
            for sc, e in zip(scenarios, elements, strict=True)
            for name in e.spending_categories
        )
    )
    demo_group = GroupSpec(
        group_name,
        (
            *(
                CategorySpec(name, assignments_are_explicit=True, tiers=tiers)
                for name, tiers in spending
            ),
            *(e.payment_category for e in elements),
        ),
        tiers=tuple(dict.fromkeys(t for sc in scenarios for t in sc.tiers)),
    )
    # A payee shared between scenarios carries the UNION of their tiers. Take
    # the first scenario's instead and a name claimed by a full-only card
    # disappears from the starter, where a both-tiers card still names it —
    # which fails generation with a bare KeyError on the payee.
    known = {p.name for p in spec.payees}
    tiers_by_payee: dict[str, tuple[str, ...]] = {}
    for sc, element in zip(scenarios, elements, strict=True):
        for name in element.payees:
            if name in known:
                continue
            merged = dict.fromkeys((*tiers_by_payee.get(name, ()), *sc.tiers))
            tiers_by_payee[name] = tuple(merged)
    new_payees = tuple(PayeeSpec(name, tiers=t) for name, t in tiers_by_payee.items())
    return replace(
        spec,
        accounts=(*spec.accounts, *(e.account for e in elements)),
        groups=(*spec.groups, demo_group),
        payees=(*spec.payees, *new_payees),
        one_offs=(*spec.one_offs, *(o for e in elements for o in e.one_offs)),
        one_off_transfers=(
            *spec.one_off_transfers,
            *(t for e in elements for t in e.transfers),
        ),
        explicit_assignments=(
            *spec.explicit_assignments,
            *(a for e in elements for a in e.assignments),
        ),
        card_scenarios=(*spec.card_scenarios, *scenarios),
    )
