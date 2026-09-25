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

from igab.domain.cards import AnchorOpenings, SetAsideState
from igab.domain.payee_names import STARTING_BALANCE_PAYEE
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
#: assign  an assignment to this card's own envelope
#: cash_spend
#:         an outflow from the budget's CASH account, filed to `category`.
#:         Touches this card's balance not at all, and reserves nothing —
#:         it is here because one situation cannot be told from another
#:         without it. A receivable ledger is a category whose charges land
#:         on whatever account was handy while the single repayment lands on
#:         one card; the spending that never reached the card is exactly what
#:         keeps the envelope at or below zero when the repayment arrives,
#:         which is the `available <= 0` half of `residual_is_pass_through`.
#:         Without a cash leg, every settle-up leaves the envelope holding
#:         the residual, and a running tab is indistinguishable from a refund
#:         an envelope kept.
EventKind = Literal[
    "spend", "charge", "refund", "pay", "deposit", "fund", "assign", "release", "cash_spend"
]

_CARD_ROWS: frozenset[str] = frozenset({"spend", "charge", "refund", "pay", "deposit"})
_NEEDS_CATEGORY: frozenset[str] = frozenset({"spend", "refund", "fund", "cash_spend"})


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
        """What this event does to the CARD's balance. 0 for assignments and
        releases (envelope moves), and 0 for `cash_spend`, which never
        touches the card."""
        if self.kind in ("spend", "charge"):
            return -self.amount
        if self.kind in ("refund", "pay", "deposit"):
            return self.amount
        return ZERO

    def signed_cash(self) -> Decimal:
        """What this event does to the budget's cash account, as a register
        row. Only `cash_spend` writes one; `pay` is a transfer, built as one."""
        return -self.amount if self.kind == "cash_spend" else ZERO


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
    #: What months ending short put on the card — the budget's own ride.
    riding: Decimal = ZERO
    #: What the budget ARRIVED with and has not yet retired. Zero on every
    #: unanchored scenario by construction; an anchored one states it here,
    #: by this name, rather than folding it into `riding` where a sentence
    #: about "a month that ended short" would quote it.
    imported_riding: Decimal = ZERO
    #: What Ready to Assign has absorbed, lifetime, because a month ended with
    #: this card's Set aside below zero. Zero on every scenario whose card
    #: never went red at a month's end — which is most of them, and says so.
    written_off: Decimal = ZERO
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
class CardLesson:
    """The situation as a READER meets it: three short beats, one line each.

    Not a second `story`. `story` says why this shape exists and what it used
    to get wrong — it becomes the docstring of every test generated from the
    scenario, and it is written for whoever is debugging the model. Pointed at
    a person trying to understand their own card it is the wrong register
    entirely: 59 to 186 words of prose about integrity bounds and residual
    legs, which is a paragraph nobody reads.

    These three answer the questions a budgeter actually asks, in the order
    they ask them. One sentence each, enforced by a test — the moment one of
    these grows a second clause about why the walk does what it does, the page
    is back to being a wall of text.

    Neither can misstate a figure: every number the Guide draws is walked by
    the card domain (`guide/card_examples.py`), not written here.
    """

    #: What the person did, or what happened to them.
    happens: str
    #: What the card row then reads — especially the part that surprises.
    reads: str
    #: What to do about it, or the words for "nothing". Several of these
    #: situations are entirely normal and saying so plainly is the answer.
    todo: str


@dataclass(frozen=True)
class BillDue:
    """When a demo card's bill falls due — the statement fact, not a position.

    Nothing in `expect` depends on it and no walk reads it: a due date is
    metadata the card row and the liability header show, and the model is
    deliberately dateless (domain/payment_due.py). It lives on the scenario
    anyway because it is a fact about a card, and card facts live here.

    `days_since_last_due` rather than a calendar date, for `cycle_days`: the
    demo has to keep demoing. A fixed anchor drifts out of the seven-day
    window the indicator fires in within a month of being written, and a
    sample budget whose feature stops showing is one nobody can check.
    """

    kind: str
    #: 'day_of_month'
    day: int | None = None
    #: 'cycle_days' — the cycle, and how long ago the last one fell due. The
    #: next due date is then `cycle_days - days_since_last_due` away.
    cycle_days: int | None = None
    days_since_last_due: int | None = None


@dataclass(frozen=True)
class CardScenario:
    slug: str
    #: The lesson the row teaches, one line. Shown beside the card in docs.
    title: str
    #: Why this shape exists and what it used to get wrong. Becomes the
    #: docstring of every test generated from it — written for whoever is
    #: debugging the model, and deliberately NOT what the Guide shows.
    story: str
    #: The same situation for a reader, in three beats. See `CardLesson`.
    lesson: CardLesson
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
    #: Which of the eight situations this card's Set aside is in, once every
    #: event has happened (domain/cards.py `SetAsideState`).
    #:
    #: Hand-written like `expect`, and required rather than defaulted: the
    #: eight are told apart by exactly the facts a reader of this file can
    #: see — was the envelope ever funded, did the money come back beyond what
    #: it charged, did a month end short — so a default would be a guess
    #: shipped as an assertion. The pure suite checks it through `state()`,
    #: and the integration suite checks the value the API actually serves.
    set_aside_state: SetAsideState = SetAsideState.FUNDED
    #: When this card's bill falls due, for the demo. None on most of them:
    #: an empty companion liability is what a real card starts as, and that
    #: is worth showing too.
    bill_due: BillDue | None = None

    @property
    def payment_category(self) -> str:
        """The card's own envelope. Named after the card, as the app does."""
        return f"{self.card} Payment"

    def categories(self) -> tuple[str, ...]:
        """Spending categories this scenario files to, in first-seen order."""
        seen: dict[str, None] = {}
        for e in self.events:
            if e.kind in ("spend", "refund", "fund", "cash_spend") and e.category:
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
        elif event.kind == "release":
            # Money moved OUT of the card's envelope: a negative assignment.
            _bump(assignments.setdefault(scenario.payment_category, {}), month, -event.amount)
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
        elif event.kind == "cash_spend":
            # The envelope's activity and NOTHING else: no card outflow, so
            # it never reserves, never rides and can never be released. It is
            # what makes the envelope's Available honest about a tab whose
            # charges did not all land on one card.
            _bump(activity.setdefault(category, {}), month, -event.amount)
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
        # Unclaimed rows are not a reserve leg, so the walk never sees them:
        # truncated at B here, exactly as `BudgetService.card_walk` truncates
        # its repository sum. Payments go into the walk untruncated — it
        # drops months before B itself. The BALANCE keeps every event:
        # register full, walk truncated.
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
    # The ledger through THIS month, not the scenario's lifetime. Every event
    # sits at or before the anchor, so this is `inputs.balance` when `through`
    # is the anchor — which is every call the suite makes. It differs the
    # moment someone asks an earlier month, which the Guide's walkthrough
    # does: a card that ends at -200 was not at -200 in its first month.
    balance = scenario.opening + sum(
        (e.signed() for e in scenario.events if e.month(today) <= month), ZERO
    )
    funding = card_funding(
        inputs.assignments,
        inputs.activity,
        inputs.outflows,
        inputs.card_categories,
        openings=inputs.openings,
        payments_by_card={scenario.card: inputs.payments},
    )
    reserve = card_reserve(funding, scenario.card)
    set_aside = reserve.set_aside(month)
    position = card_position(set_aside, balance)
    written_off = sum_through(reserve.written_off, month)
    # The month ledger, summed straight off the events — deliberately a
    # different path from the SQL (`card_month_flows`) the served figure
    # takes, so the two check each other through the shared expectations.
    month_events = [e for e in scenario.events if e.month(today) == month]
    charged = sum((e.amount for e in month_events if e.kind in ("spend", "charge")), ZERO)
    inflows = sum((e.amount for e in month_events if e.kind in ("refund", "pay", "deposit")), ZERO)
    paid = sum((e.amount for e in month_events if e.kind == "pay"), ZERO)
    return ExpectedPosition(
        balance=balance,
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
        imported_riding=sum_through(funding.imported_riding_by_card.get(scenario.card, {}), month),
        written_off=written_off,
        # The serving arithmetic exactly (budget_service.get_budget_summary):
        # the opening reserve and every write-off fold into `assigned`, and
        # `opening_credit` is the T3 allowance — this checker must not drift
        # from what is served.
        reserve_discrepancy=reserve_discrepancy(
            set_aside,
            balance,
            sum_through(reserve.opening, month)
            + sum_through(reserve.assignments, month)
            + written_off,
            sum_through(funding.covered_by_card.get(scenario.card, {}), month),
            sum_through(reserve.payments, month),
            sum_through(reserve.residual, month),
            sum_through(inputs.unclaimed, month),
            opening_credit=inputs.opening_credit,
            written_off=written_off,
        ),
    )


def state(scenario: CardScenario, today: date, through: date | None = None) -> SetAsideState:
    """Run a scenario through the real domain and report which of the eight
    situations its card is in.

    The sibling of `walk` and used the same way: to CHECK
    `CardScenario.set_aside_state`, never to produce it.

    The ledger sweep here reads `end_balances` — every category the walk
    touched, with the card correction already folded in — which is the same
    figure `BudgetService` hands `receivable_ledgers`, reached by a different
    route. A scenario category absent from it never met a card and cannot be
    a ledger.
    """
    from igab.domain.cards import (
        card_funding,
        card_position,
        card_reserve,
        receivable_ledgers,
        residual_from,
        ride_is_exclusive,
        set_aside_state,
    )
    from igab.domain.carryover import available_at, sum_through

    inputs = to_funding_inputs(scenario, today)
    month = through or date(today.year, today.month, 1)
    balance = scenario.opening + sum(
        (e.signed() for e in scenario.events if e.month(today) <= month), ZERO
    )
    funding = card_funding(
        inputs.assignments,
        inputs.activity,
        inputs.outflows,
        inputs.card_categories,
        openings=inputs.openings,
        payments_by_card={scenario.card: inputs.payments},
    )
    reserve = card_reserve(funding, scenario.card)
    position = card_position(reserve.set_aside(month), balance)
    ledgers = receivable_ledgers(
        {category: list(series.values()) for category, series in inputs.assignments.items()},
        {
            category: available_at(series, month)
            for category, series in funding.end_balances.items()
        },
    )
    # This month's figures, as budget_service reads them: a shortfall is
    # always this month's, since last month's was written off.
    return set_aside_state(
        position,
        residual=reserve.residual.get(month, ZERO),
        # The budget's own ride only — imported debt has no month to fund.
        riding=sum_through(funding.riding_by_card.get(scenario.card, {}), month),
        residual_from_ledgers=residual_from(
            funding.residual_by_pair, scenario.card, ledgers, month
        ),
        ride_reaches_this_card=ride_is_exclusive(funding.floored_by_pair, scenario.card, month),
        released_out=max(ZERO, -reserve.assignments.get(month, ZERO)),
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


def _release(months_ago: int, amount: str) -> CardEvent:
    """Move `amount` OUT of the card's envelope — the Release button, or a
    negative typed into Assigned. Stated positive; applied as a negative
    assignment everywhere it is walked."""
    return CardEvent(RelDate(months_ago, 1), "release", Decimal(amount))


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


def _cash_spend(months_ago: int, amount: str, category: str, day: int = 14) -> CardEvent:
    """An outflow from the budget's cash account, filed to `category`. Reaches
    this card not at all — see the `cash_spend` note on `EventKind`."""
    return CardEvent(RelDate(months_ago, day), "cash_spend", Decimal(amount), category)


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
    set_aside_state=SetAsideState.FUNDED,
    lesson=CardLesson(
        happens="You budget for what you buy, swipe the card, and pay the bill from checking.",
        reads=(
            "Set aside always matches what the card owes, and paying the bill empties both "
            "together."
        ),
        todo="Nothing. This is the loop working.",
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
    # Billed every 31 days, last due 28 days ago: the next one is three days
    # out, so the strip's chip and the header's warning tone are both on in
    # a freshly generated sample. The card owing $2,600 is the one where a
    # due date is worth knowing about.
    bill_due=BillDue(kind="cycle_days", cycle_days=31, days_since_last_due=28),
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
    set_aside_state=SetAsideState.FUNDED,
    lesson=CardLesson(
        happens=(
            "The card arrived carrying old debt, so each month you fund your spending and "
            "assign something extra to the card on top."
        ),
        reads=(
            "What is not covered falls by exactly what you assign. Set aside only holds this "
            "month's spending plus that assignment until you pay."
        ),
        todo=(
            "Keep assigning what you can afford, then pay by transfer. The part not covered is "
            "the debt, and it shrinks as you go."
        ),
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
    # The ordinary shape beside it, so the sample shows both and the
    # difference between them is visible in one screen.
    bill_due=BillDue(kind="day_of_month", day=17),
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
    set_aside_state=SetAsideState.FUNDED,
    lesson=CardLesson(
        happens=(
            "You spent $100 on the card out of an envelope holding $40, and the month ended "
            "before you could fund the rest."
        ),
        reads=(
            "The $60 the envelope could not cover rides onto the card as debt not covered. "
            "Ready to Assign is never charged for it."
        ),
        todo=(
            "Go back to that month and raise the envelope's assignment — the ride disappears. "
            "Funding it this month does not reach back."
        ),
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
    # In the quick demo too. It showed two funded cards and nothing else, so
    # the one affordance on the strip — Release — was never seen. This is
    # the card state that is common, harmless, and has a button: a surplus
    # on a card paid from funded envelopes. The below-zero states stay in
    # the full tour on purpose — the first row a new user sees must not be
    # an oddity (test_sample_budget.py says why).
    tiers=BOTH_TIERS,
    set_aside_state=SetAsideState.SURPLUS,
    lesson=CardLesson(
        happens=(
            "You assign money to the card every month, but there is never any riding debt for "
            "it to retire."
        ),
        reads="Set aside climbs past what the card owes, and the extra reads as spare.",
        todo="Release the spare and it goes back to Ready to Assign, or into another envelope.",
    ),
)

SETTLED_BY_OTHERS = CardScenario(
    slug="settled-by-others",
    title="A running tab, settled in one go",
    story=(
        "Somebody else's spending is tracked as a running tab rather than "
        "funded as an envelope: never assigned to, allowed to go red as their "
        "charges land, squared up when they pay. Their charges land on "
        "whatever was handy — some on this card, some straight out of "
        "checking — while the one repayment lands on this card. It pays the "
        "card down by more than the tab ever charged HERE, so the excess "
        "reduces Set aside without releasing any envelope's cash and drives "
        "it below zero.\n\n"
        "Nothing is wrong and there is nothing to do: the household paid this "
        "card down by exactly as much as Set aside gave up, and the tab is "
        "holding none of the money. The 200 below zero is covered from Ready "
        "to Assign on the 1st, and in exchange the card owes 200 less. Told "
        "apart from a refund an envelope kept by two facts and no threshold — "
        "the tab was NEVER assigned to, and "
        "it is holding nothing now (`residual_is_pass_through`). The cash "
        "leg is what makes the second true: without spending that never "
        "reached the card, a settle-up always leaves the envelope holding the "
        "residual, and this situation is indistinguishable from the one it "
        "must not be confused with."
    ),
    card="Thistledown Card",
    short="Thistledown",
    opening=_d("-800"),
    events=(
        # The funded side of the budget, so this card is not a card where
        # nothing was ever assigned anywhere — the ledger test is about ONE
        # envelope, and a scenario that cannot tell the two apart proves
        # nothing.
        _fund(2, "100", "Thistledown Groceries"),
        _spend(2, "100", "Thistledown Groceries"),
        _spend(2, "200", "Thistledown Shared Tab"),
        _fund(1, "100", "Thistledown Groceries"),
        _spend(1, "100", "Thistledown Groceries"),
        _spend(1, "200", "Thistledown Shared Tab"),
        # The settle-up month: another 200 of their charges on the card, 400
        # more fronted in cash, and 1,000 back when they square up.
        _spend(0, "200", "Thistledown Shared Tab", day=1),
        _cash_spend(0, "400", "Thistledown Shared Tab", day=1),
        _refund(0, "1000", "Thistledown Shared Tab", day=1),
    ),
    # Hand-computed. The tab rode 200 in each of the first two months (its
    # whole shortfall, capped at what it charged the card), so 400 was riding
    # when the repayment arrived. The repayment is 1,000 against 200 charged
    # here that month — an 800 inflow — which discharges the 400 riding and
    # leaves 400 with nowhere to go but Set aside: 200 reserved by groceries,
    # less 400, is -200. The tab itself ends at exactly zero, which is what a
    # squared-up tab looks like and what makes it a ledger rather than an
    # envelope holding card money.
    expect=ExpectedPosition(
        balance=_d("-600"),
        set_aside=_d("-200"),
        uncovered=_d("600"),
        short_reserved=_d("200"),
        charged_this_month=_d("200"),
        inflows_this_month=_d("1000"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("800"),
    ),
    set_aside_state=SetAsideState.SETTLED_BY_OTHERS,
    tiers=("full",),
    lesson=CardLesson(
        happens=(
            "Somebody else's spending goes on a tab you never budget into — some on this card, "
            "some out of checking — and they settle up in one payment onto the card."
        ),
        reads=(
            "The card reads overspent, −$200: they paid it down by more than the tab ever "
            "charged it."
        ),
        todo=(
            "Nothing. Next month's Ready to Assign covers the $200, and the card owes $200 less "
            "— the same as assigning it to the card."
        ),
    ),
)

RIDE_UNFUNDED = CardScenario(
    slug="ride-unfunded",
    title="A month ended short, and the payment covered what was reserved and the ride",
    story=(
        "An envelope was funded 100 and spent 300 on this card, so 200 rode "
        "onto the card when the month ended. A later payment covered "
        "everything that WAS reserved and the ride as well, and Set aside "
        "went below zero by exactly the ride.\n\n"
        "The remedy is the one this row may promise, and only here: the whole "
        "of that envelope's shortfall rode onto THIS card, so raising that "
        "month's assignment retires the ride — the walk is recomputed from "
        "scratch on every request. The moment a shortfall is shared with "
        "another card the promise is false (`ride_is_exclusive`), which is "
        "why the state is decided from the pair table and not from the fact "
        "that something is riding."
    ),
    card="Bramblewick Card",
    short="Bramblewick",
    opening=_d("-200"),
    events=(
        _fund(2, "100", "Bramblewick Hardware"),
        _spend(2, "300", "Bramblewick Hardware"),
        _fund(1, "100", "Bramblewick Hardware"),
        _spend(1, "100", "Bramblewick Hardware"),
        _pay(0, "400", day=1),
    ),
    # Hand-computed. Reserved 100 + 100 = 200 against a 400 payment, so Set
    # aside is -200 — the ride, exactly. The first month's envelope was 200
    # short and its whole shortfall rode here. The card owes
    # 200 + 300 + 100 - 400 = 200.
    #
    # It used to pay 500 and sit at -300 with 200 riding: a ride that
    # explained two thirds of the shortfall, labelled as if it explained all
    # of it, with a remedy that would have left the card 100 short. That
    # shape is `mixed` now, and has its own scenario below.
    expect=ExpectedPosition(
        balance=_d("-200"),
        set_aside=_d("-200"),
        uncovered=_d("200"),
        short_reserved=_d("200"),
        riding=_d("200"),
        charged_this_month=_d("0"),
        inflows_this_month=_d("400"),
        paid_this_month=_d("400"),
        debt_change_this_month=_d("400"),
    ),
    set_aside_state=SetAsideState.RIDE_UNFUNDED,
    tiers=("full",),
    lesson=CardLesson(
        happens=(
            "An envelope funded $100 spent $300 on the card, so $200 rode onto the card — and "
            "then you paid the bill."
        ),
        reads=(
            "The payment ran past what was actually set aside, so the card reads overspent: −$200."
        ),
        todo=(
            "Raise that month's assignment on the envelope, or assign $200 to the card this "
            "month. Otherwise it comes out of next month's Ready to Assign."
        ),
    ),
)

MIXED = CardScenario(
    slug="mixed",
    title="Two things overspent the card, and neither explains all of it",
    story=(
        "The settle-up card, plus one ordinary decision. Somebody else's "
        "spending ran through a tab you never budget into, and when they "
        "squared up, 400 of it landed as residual — that is the whole of the "
        "card two rows up. Here the household ALSO paid 300 off the card from "
        "cash nothing had set aside. Set aside is 500 below zero: 400 of it "
        "somebody else's settle-up, 300 a paydown, 200 of it reserved by "
        "groceries and consumed.\n\n"
        "This is the shape a real budget is usually in, and the one the "
        "eight-state model had no word for. It fell through every branch to "
        "'paid ahead' and quoted the full 500 as money you had paid — 400 of "
        "which was somebody else's. The row does not decompose it now, because "
        "it cannot: the reserve identity is bounds, not parts. It names what "
        "is present, quotes each served leg, and points at the breakdown."
    ),
    card="Marrowbone Card",
    short="Marrowbone",
    opening=_d("-800"),
    events=(
        _fund(2, "100", "Marrowbone Groceries"),
        _spend(2, "100", "Marrowbone Groceries"),
        _spend(2, "200", "Marrowbone Shared Tab"),
        _fund(1, "100", "Marrowbone Groceries"),
        _spend(1, "100", "Marrowbone Groceries"),
        _spend(1, "200", "Marrowbone Shared Tab"),
        _spend(0, "200", "Marrowbone Shared Tab", day=1),
        _cash_spend(0, "400", "Marrowbone Shared Tab", day=1),
        _refund(0, "1000", "Marrowbone Shared Tab", day=1),
        # The second cause: 300 paid off the card out of ordinary cash.
        _pay(0, "300", day=1),
    ),
    # Hand-computed. As `settled-by-others`: 200 reserved, 400 residual after
    # the 400 riding is discharged, so -200. Then a 300 payment nothing
    # reserved for: -500. The card owes 800 opening + 800 charged (300 + 300
    # + 200) - 1000 refunded - 300 paid = 300. The ledger's residual (400) is
    # less than the shortfall (500), so no single branch claims it — and 300
    # of the 500 is not the settle-up.
    expect=ExpectedPosition(
        balance=_d("-300"),
        set_aside=_d("-500"),
        uncovered=_d("300"),
        short_reserved=_d("500"),
        charged_this_month=_d("200"),
        inflows_this_month=_d("1300"),
        paid_this_month=_d("300"),
        debt_change_this_month=_d("1100"),
    ),
    set_aside_state=SetAsideState.MIXED,
    tiers=("full",),
    lesson=CardLesson(
        happens=(
            "Somebody settled up $1,000 of tab charges on this card — and separately you paid "
            "$300 off it from cash."
        ),
        reads=(
            "The card reads overspent, −$500. The row names both causes, a $400 settle-up and "
            "payments past the reserve, and does not split the $500."
        ),
        todo=(
            "Assign $500 to the card this month, or it comes out of next month's Ready to "
            "Assign. The breakdown has each figure."
        ),
    ),
)

MOVED_OUT = CardScenario(
    slug="moved-out",
    title="More was moved out of the card's envelope than it held",
    story=(
        "A card paid in full every month, so its envelope holds exactly the "
        "bill: 300 reserved by 300 of funded spending. The household needs "
        "cash elsewhere this month and releases 500 from the envelope — 200 "
        "more than was there.\n\n"
        "No payment happened and nothing came back onto the card, so the "
        "money is in Ready to Assign and the envelope is simply overdrawn by "
        "200. This used to read 'paid ahead' — 'you have paid $200 more "
        "toward this card than any envelope set aside; the money has already "
        "left your account' — about money that had left nothing but this "
        "envelope. The remedy is the same word, assign, for the opposite "
        "reason: not to record a payment, but to put back what was taken."
    ),
    card="Wrenfield Card",
    short="Wrenfield",
    opening=_d("0"),
    events=(
        _fund(1, "300", "Wrenfield Groceries"),
        _spend(1, "300", "Wrenfield Groceries"),
        _release(0, "500"),
    ),
    # Hand-computed. 300 reserved by the funded spend; 500 moved out; Set
    # aside -200. The card still owes the 300 it was charged and nothing has
    # been paid, so it is 300 uncovered — 500 of it the release, less 200 that
    # was never there to begin with.
    expect=ExpectedPosition(
        balance=_d("-300"),
        set_aside=_d("-200"),
        uncovered=_d("300"),
        short_reserved=_d("200"),
        charged_this_month=_d("0"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("0"),
    ),
    set_aside_state=SetAsideState.MOVED_OUT,
    tiers=("full",),
    lesson=CardLesson(
        happens=(
            "An envelope held $300 for the bill, and you moved $500 out of it to use elsewhere."
        ),
        reads=(
            "The card reads overspent, −$200, and the row says the money was moved out, not paid."
        ),
        todo=(
            "Assign $200 back to the card this month, or it comes out of next month's Ready to "
            "Assign."
        ),
    ),
)

PAID_AHEAD = CardScenario(
    slug="paid-ahead",
    title="Paid more than was ever set aside",
    story=(
        "A card carrying debt from before the budget, paid deliberately "
        "faster than the envelopes reserve. Two funded months set 400 aside "
        "and a 700 payment went out, so 300 of it came from money no envelope "
        "was holding and went straight to the balance.\n\n"
        "Nothing came back onto the card and no month ended short, so there "
        "is nothing to re-file and no envelope to back-fund: this is the plain "
        "case the other negatives are mistaken for. The card is overspent by "
        "300: assign 300 to it this month, or the 1st takes the 300 out of "
        "next month's Ready to Assign. (Option (b), shipped briefly, charged "
        "Ready to Assign the moment the card was paid instead; YNAB, and now "
        "this, treat it as the card envelope's overspending.)"
    ),
    card="Quillon Card",
    short="Quillon",
    opening=_d("-1000"),
    events=(
        _fund(2, "200", "Quillon Fuel"),
        _spend(2, "200", "Quillon Fuel"),
        _fund(1, "200", "Quillon Fuel"),
        _spend(1, "200", "Quillon Fuel"),
        _pay(0, "700", day=1),
    ),
    # Hand-computed. Reserved 200 + 200 = 400, paid 700, so Set aside is -300
    # with nothing riding and nothing returned. The card owes
    # 1000 + 200 + 200 - 700 = 700, all of it uncovered.
    expect=ExpectedPosition(
        balance=_d("-700"),
        set_aside=_d("-300"),
        uncovered=_d("700"),
        short_reserved=_d("300"),
        charged_this_month=_d("0"),
        inflows_this_month=_d("700"),
        paid_this_month=_d("700"),
        debt_change_this_month=_d("700"),
    ),
    set_aside_state=SetAsideState.PAID_AHEAD,
    tiers=("full",),
    lesson=CardLesson(
        happens="You paid $700 toward a card carrying old debt when only $400 had been set aside.",
        reads="The extra $300 went straight to the balance, so the card reads overspent: −$300.",
        todo=(
            "Assign $300 to the card this month, or it comes out of next month's Ready to Assign."
        ),
    ),
)

REIMBURSED = CardScenario(
    slug="reimbursed",
    title="Somebody else paid part of the bill",
    story=(
        "A share of the bill is settled by someone else and filed to the "
        "category that tracks what they owe. That category never charged this "
        "card, so there is nothing to hand back to it: the money reduces the "
        "card's Set aside without releasing any envelope's cash, and Set aside "
        "goes below zero this month while the card still owes thousands. That "
        "is overspending on the card's envelope: unless the difference is "
        "assigned before the month ends, next month's Ready to Assign covers it."
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
        _refund(0, "500", "Alder Grove Shared Expenses", day=1),
        _fund(0, "200", "Alder Grove Groceries"),
        _spend(0, "200", "Alder Grove Groceries", day=1),
    ),
    # Hand-computed. Month 2: +200 reserved, −200 paid → 0. Month 1: +200.
    # This month: the 500 settle-up releases nothing (the envelope never
    # charged here) → −300, then +200 reserved → −100. Nothing earlier ended
    # below zero, so nothing has been written off yet.
    expect=ExpectedPosition(
        balance=_d("-1900"),
        set_aside=_d("-100"),
        uncovered=_d("1900"),
        short_reserved=_d("100"),
        charged_this_month=_d("200"),
        inflows_this_month=_d("500"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("300"),
    ),
    tiers=("full",),
    set_aside_state=SetAsideState.REFUND_OUTRAN_ENVELOPE,
    lesson=CardLesson(
        happens=(
            "Somebody paid $500 back onto the card, filed to an envelope that had never charged "
            "this card."
        ),
        reads=(
            "That envelope gained $500. The card reads overspent, −$100, while it still owes "
            "$1,900."
        ),
        todo=(
            "Move $100 from that envelope to the card this month, or it comes out of next "
            "month's Ready to Assign."
        ),
    ),
)


REFUND_WRITTEN_OFF = CardScenario(
    slug="refund-written-off",
    title="A refund to another envelope, covered by the next month",
    story=(
        "The same settle-up as the reimbursed card, a month earlier. Set aside "
        "ended that month below zero, so the next month's Ready to Assign "
        "covered it — exactly as it covers any overspent envelope — and the "
        "card started the month at zero. The envelope that took the settle-up "
        "keeps the money; Ready to Assign paid for it."
    ),
    card="Wren Card",
    short="Wren",
    opening=_d("-2000"),
    events=(
        _fund(2, "200", "Wren Groceries"),
        _spend(2, "200", "Wren Groceries"),
        _pay(2, "200"),
        _fund(1, "200", "Wren Groceries"),
        _spend(1, "200", "Wren Groceries"),
        _refund(1, "500", "Wren Shared Expenses"),
        _fund(0, "200", "Wren Groceries"),
        _spend(0, "200", "Wren Groceries", day=1),
    ),
    # Hand-computed. Month 2 ends at 0. Month 1: +200 reserved, −500 of
    # settle-up the envelope never charged → −300 at month end. This month
    # opens with the 300 written off (→ 0), then +200 reserved.
    expect=ExpectedPosition(
        balance=_d("-1900"),
        set_aside=_d("200"),
        uncovered=_d("1700"),
        written_off=_d("300"),
        charged_this_month=_d("200"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-200"),
    ),
    tiers=("full",),
    set_aside_state=SetAsideState.FUNDED,
    lesson=CardLesson(
        happens=(
            "Last month somebody paid $500 onto the card, filed to an envelope that had never "
            "charged it, and nothing was moved to the card before the month ended."
        ),
        reads=(
            "This month the card started at $0. Its $300 of overspending came out of Ready "
            "to Assign on the 1st."
        ),
        todo="Nothing. The envelope that took the $500 still holds it.",
    ),
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
    # Hand-computed. Each of the first two months: +60 reserved, −200 paid
    # → −140, written off on the 1st of the next (2 × 140 = 280). This month
    # starts at 0 and reserves 60. The card holds 220 of the household's
    # money: 400 paid against 180 charged.
    expect=ExpectedPosition(
        balance=_d("220"),
        set_aside=_d("60"),
        uncovered=_d("0"),
        over_reserved=_d("60"),
        card_credit=_d("220"),
        written_off=_d("280"),
        charged_this_month=_d("60"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-60"),
    ),
    tiers=("full",),
    set_aside_state=SetAsideState.CARD_HOLDS_IT,
    lesson=CardLesson(
        happens="You paid the card more than it owed, month after month.",
        reads=(
            "The balance is positive: the card is holding your money. Each overpayment was "
            "overspending for its month, and came out of the next month's Ready to Assign."
        ),
        todo="Nothing. Later spending on the card will use the credit up.",
    ),
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
        "uncovered while Set aside sat at zero."
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
    set_aside_state=SetAsideState.FUNDED,
    lesson=CardLesson(
        happens="Charges land on the card and nobody files them to an envelope.",
        reads=(
            "Set aside stays at $0.00 and the whole balance reads as not covered, because no "
            "envelope was ever charged."
        ),
        todo=(
            "File them. It takes no money you do not have — it just tells your reports where "
            "the money went."
        ),
    ),
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
    set_aside_state=SetAsideState.FUNDED,
    lesson=CardLesson(
        happens=(
            "A payment reached the card as a plain credit, never linked to the money that left "
            "checking."
        ),
        reads=(
            "The balance falls but Set aside does not move, because only a linked transfer "
            "spends Set aside."
        ),
        todo="Link the two halves under Account suggestions on the Accounts page.",
    ),
)

PAID_AHEAD_WRITTEN_OFF = CardScenario(
    slug="paid-ahead-written-off",
    title="A payment ran ahead of the reserve, and the next month covered it",
    story=(
        "The statement was paid in full — but it included debt carried in "
        "from before the budget, which nothing had reserved against, so the "
        "payment drove Set aside below zero. Nothing was assigned to the card "
        "before the month ended, so the next month's Ready to Assign covered "
        "it, as it covers any overspent envelope, and the card started that "
        "month at zero. Funded spending since has built it back up."
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
    # Hand-computed. Month 2: +100 reserved, −250 paid → −150, written off
    # on the 1st of month 1 (→ 0), then +200 reserved → 200. This month: −50
    # paid → 150. Owed 300 − 150 set aside = 150 uncovered.
    expect=ExpectedPosition(
        balance=_d("-300"),
        set_aside=_d("150"),
        uncovered=_d("150"),
        written_off=_d("150"),
        charged_this_month=_d("0"),
        inflows_this_month=_d("50"),
        paid_this_month=_d("50"),
        debt_change_this_month=_d("50"),
    ),
    tiers=("full",),
    set_aside_state=SetAsideState.FUNDED,
    lesson=CardLesson(
        happens=(
            "The statement included debt from before the budget, so paying it in full ran past "
            "what had been set aside."
        ),
        reads=(
            "That month the card showed overspent. On the 1st the $150 came out of Ready to "
            "Assign and the card started again at $0."
        ),
        todo=(
            "Nothing now. To keep it from reaching Ready to Assign, assign the difference to "
            "the card in the month it happens."
        ),
    ),
)


PAID_AHEAD_COVERED = CardScenario(
    slug="paid-ahead-covered",
    title="A payment ran ahead of the reserve, covered the same month",
    story=(
        "A big payment on debt from before the budget ran past what was set "
        "aside, and the difference was assigned to the card in the same "
        "month. The card never ends a month overspent, so nothing reaches "
        "Ready to Assign on the 1st — the assignment already paid for it."
    ),
    card="Juniper Card",
    short="Juniper",
    opening=_d("-1000"),
    events=(
        _fund(2, "200", "Juniper Groceries"),
        _spend(2, "200", "Juniper Groceries"),
        _fund(1, "200", "Juniper Groceries"),
        _spend(1, "200", "Juniper Groceries"),
        _assign(0, "300"),
        _pay(0, "700", day=1),
    ),
    # Hand-computed. 200 + 200 reserved = 400; this month +300 assigned,
    # −700 paid → 0. Owed 1000 + 400 − 700 = 700, none of it set aside.
    expect=ExpectedPosition(
        balance=_d("-700"),
        set_aside=_d("0"),
        uncovered=_d("700"),
        charged_this_month=_d("0"),
        inflows_this_month=_d("700"),
        paid_this_month=_d("700"),
        debt_change_this_month=_d("700"),
    ),
    tiers=("full",),
    set_aside_state=SetAsideState.FUNDED,
    lesson=CardLesson(
        happens=(
            "You paid $700 toward the card with $400 set aside, and assigned the other $300 "
            "to the card that month."
        ),
        reads="Set aside is back at $0. Nothing was overspent, so nothing carries over.",
        todo="Nothing. This is the way to pay down old debt without touching next month.",
    ),
)

#: Order is the order the demo shows them: the healthy card first, so the
#: strip does not open on an oddity the way it used to.
ALL_SCENARIOS: tuple[CardScenario, ...] = (
    PAID_IN_FULL,
    CARRYING_DEBT,
    MONTH_ENDED_SHORT,
    OVER_RESERVED,
    REIMBURSED,
    REFUND_WRITTEN_OFF,
    UNFILED_SPENDING,
    UNLINKED_PAYMENT,
    PAID_AHEAD_WRITTEN_OFF,
    PAID_AHEAD_COVERED,
    CREDIT_BALANCE,
    SETTLED_BY_OTHERS,
    RIDE_UNFUNDED,
    PAID_AHEAD,
    MIXED,
    MOVED_OUT,
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
        # Nothing of this budget's own rides: today's spend was funded. What
        # is still riding is what the import brought, less the 250 retired —
        # named as such, so no row calls it spending from a month that ended
        # short.
        riding=_d("0"),
        imported_riding=_d("150"),
        charged_this_month=_d("100"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-100"),
        reserve_discrepancy=_d("0"),
    ),
    set_aside_state=SetAsideState.FUNDED,
    lesson=CardLesson(
        happens="The budget was imported from YNAB partway through the card's life.",
        reads=(
            "Set aside opens at the position YNAB had, and the months before the import stay in "
            "the register and reports rather than being re-walked."
        ),
        todo="Nothing. The import seam is labelled in the month-by-month history.",
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
    set_aside_state=SetAsideState.CARD_HOLDS_IT,
    lesson=CardLesson(
        happens="The card was already holding a credit on the day the budget was imported.",
        reads=(
            "The card reads as holding your money from the first day, with nothing before the "
            "import to explain it."
        ),
        todo="Nothing. Later spending on the card will absorb it.",
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
    set_aside_state=SetAsideState.SURPLUS,
    lesson=CardLesson(
        happens="A card imported in credit was then spent down until it owed money again.",
        reads="Set aside sits above what the card owes, and the difference reads as spare.",
        todo="Release the spare if you want it back, or leave it against the next bill.",
    ),
)

#: Anchored shapes, beside — never inside — ALL_SCENARIOS: one budget has one
#: anchor, and splicing one into the demo would truncate every other
#: scenario's history. `merge_into` refuses them; `build_scenario_spec`
#: builds them a budget of their own.
ANCHORED_NEGATIVE_OPENING = CardScenario(
    slug="anchored-negative-opening",
    title="A YNAB import whose card envelope was overspent",
    story=(
        "YNAB showed the card's payment category in the red when the budget "
        "was imported. That is overspending, so the first imported month "
        "covers it from Ready to Assign — the same rule an overspent "
        "category opening follows — and it retires that much of the debt the "
        "import brought in."
    ),
    card="Heron Visa",
    short="Heron",
    opening=_d("-200"),
    # At B−1 the card owes 500 (200 carried in, 300 charged before the
    # anchor) and YNAB's CCP Available reads −120, so the importer's
    # max(0, −balance − ccp) puts 620 riding uncovered.
    import_anchor=CardAnchor(months_ago=2, reserve=_d("-120"), uncovered=_d("620")),
    events=(
        # Before B: register history the walk does not re-derive.
        _spend(3, "300", "Heron Groceries"),
        _fund(0, "100", "Heron Groceries"),
        _spend(0, "100", "Heron Groceries", day=1),
    ),
    tiers=("full",),
    # Hand-computed. B opens with the −120 written off (→ 0), which retires
    # 120 of the 620 opening ride → 500. Today +100 reserved. Owed 600 − 100
    # set aside = 500 uncovered, all of it what the import brought.
    expect=ExpectedPosition(
        balance=_d("-600"),
        set_aside=_d("100"),
        uncovered=_d("500"),
        riding=_d("0"),
        imported_riding=_d("500"),
        written_off=_d("120"),
        charged_this_month=_d("100"),
        inflows_this_month=_d("0"),
        paid_this_month=_d("0"),
        debt_change_this_month=_d("-100"),
        reserve_discrepancy=_d("0"),
    ),
    set_aside_state=SetAsideState.FUNDED,
    lesson=CardLesson(
        happens="The budget was imported from YNAB while this card's payment category was red.",
        reads=(
            "The first imported month covered the $120 from Ready to Assign, and the card "
            "started at $0."
        ),
        todo="Nothing. It was handled the way YNAB would have handled it.",
    ),
)


ANCHORED_SCENARIOS: tuple[CardScenario, ...] = (
    ANCHORED_IMPORT,
    ANCHORED_IN_CREDIT,
    ANCHORED_CREDIT_SPENT_DOWN,
    ANCHORED_NEGATIVE_OPENING,
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
                payee=STARTING_BALANCE_PAYEE,
                amount=scenario.opening,
                # Filed nowhere: on a card the opening gap is debt the budget
                # never funded, not income to assign.
                category=None,
                memo="Starting balance",
                tiers=scenario.tiers,
            )
        )

    for event in scenario.events:
        if event.kind == "cash_spend":
            one_offs.append(
                OneOffTxn(
                    when=event.when,
                    account=cash_account,
                    payee=_payee_for(event, scenario),
                    amount=event.signed_cash(),
                    category=event.category,
                    tiers=scenario.tiers,
                )
            )
        elif event.kind in ("spend", "charge", "refund", "deposit"):
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
        elif event.kind in ("fund", "assign", "release"):
            assignments.append(
                ExplicitAssignment(
                    category=(
                        scenario.payment_category
                        if event.kind in ("assign", "release")
                        else event.category or ""
                    ),
                    when=RelDate(event.when.months_ago, 1),
                    # A release is the same row with the sign flipped: the
                    # generator adds assignments, so a negative one subtracts.
                    amount=-event.amount if event.kind == "release" else event.amount,
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
    "cash_spend": "Corner Market",
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
            + [STARTING_BALANCE_PAYEE, "Employer Payroll", "Thai Garden", "Netflix", "Amazon"]
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

    Each scenario brings its own account, its own card's envelope and its own
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
