"""What one movement of money does, told from the rules that decide it.

The Guide's "How money counts" tab lets someone move $1,000 between two kinds
of account and see what happens: which class each leg lands in, which reports
count it, what the savings rate does, and which budget figure moves. Every one
of those answers already has a home, and this module owns none of them:

- **the class** is `activity_class._rules`, evaluated over literal booleans by
  the service (`literal_class_query`) — this module only says which booleans a
  hypothetical leg carries (`leg_facts`);
- **where a category may sit** is `transfers.leg_may_carry_category`;
- **which reports count a class** is the class tuples in `activity_class`;
- **the savings rates** are `activity_class.savings_rates`.

The one thing that is new here is `budget_terms`: which budget figure a move
changes. That is prose about `BudgetService`'s arithmetic, which cannot be
evaluated over literals the way the rules can — it is a walk over months,
envelopes and cards. So it is irreducible, and it is pinned instead by a
differential test (`tests/integration/test_money_moves_agreement.py`) that
builds every shape combination with real accounts and transfers and holds the
served term to the service's actual month deltas.

It describes one calm situation, stated as `ASSUMPTION`: the envelope already
holds the money, and a card owed nothing before the move. Outside it the card
model has texture this table does not claim — a payment against uncovered
debt, an inflow onto a card that owes more than is set aside — and the
explorer says so rather than pretending one answer fits.

Pure throughout: plain records in, verdicts out, no session.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from igab.domain.activity_class import (
    COST_OF_LIVING_CLASSES,
    PLANNED_SPEND_TAG_KEYS,
    SAVINGS_RATE_NUMERATORS,
    SPENDING_CLASSES,
    TAG_INPUT_KEYS,
    ActivityClass,
    ActivityReason,
    LegFacts,
    class_magnitude,
    savings_rates,
)
from igab.domain.transfers import leg_may_carry_category

#: The situation `budget_terms` describes. Served beside every answer.
ASSUMPTION = (
    "Assumes the category already holds the money and a credit card owed nothing before the move."
)


class MoveKind(StrEnum):
    #: Two linked legs: money leaves one account you track and arrives in another.
    TRANSFER = "transfer"
    #: One leg: money arrives from, or leaves to, someone outside.
    TRANSACTION = "transaction"


class Direction(StrEnum):
    IN = "in"
    OUT = "out"


class CategoryKind(StrEnum):
    """The kind of category a move is filed under. The two tag kinds carry the
    system tag key they read (`TAG_INPUT_KEYS`), so no second spelling exists."""

    NONE = "none"
    ORDINARY = "ordinary"
    SAVINGS = "savings"
    DEBT_PRINCIPAL = "debt_principal"
    #: A category in a system (Income) group — Ready to Assign.
    INCOME = "income"


class LegRole(StrEnum):
    FROM = "from"
    TO = "to"
    #: The single leg of a plain transaction.
    ACCOUNT = "account"


class BudgetTerm(StrEnum):
    READY_TO_ASSIGN = "ready_to_assign"
    ENVELOPE = "envelope"
    CARD_SET_ASIDE = "card_set_aside"
    CARD_UNCOVERED = "card_uncovered"


class ReportFamily(StrEnum):
    INCOME = "income"
    SPENDING = "spending"
    COST_OF_LIVING = "cost_of_living"
    SAVINGS_RATE = "savings_rate"
    SAVINGS_RATE_WITH_DEBT = "savings_rate_with_debt"


#: Which classes each report family counts — read from the tuples the reports
#: themselves read, never listed again.
REPORT_FAMILY_CLASSES: dict[ReportFamily, tuple[ActivityClass, ...]] = {
    ReportFamily.INCOME: (ActivityClass.INCOME,),
    ReportFamily.SPENDING: SPENDING_CLASSES,
    ReportFamily.COST_OF_LIVING: COST_OF_LIVING_CLASSES,
    ReportFamily.SAVINGS_RATE: SAVINGS_RATE_NUMERATORS[ReportFamily.SAVINGS_RATE.value],
    ReportFamily.SAVINGS_RATE_WITH_DEBT: SAVINGS_RATE_NUMERATORS[
        ReportFamily.SAVINGS_RATE_WITH_DEBT.value
    ],
}

REPORT_FAMILY_LABEL: dict[ReportFamily, str] = {
    ReportFamily.INCOME: "Income",
    ReportFamily.SPENDING: "Spending reports",
    ReportFamily.COST_OF_LIVING: "Cost of living",
    ReportFamily.SAVINGS_RATE: "Savings rate",
    ReportFamily.SAVINGS_RATE_WITH_DEBT: "Savings rate with debt",
}


@dataclass(frozen=True)
class AccountShape:
    """The three facts about an account the rules and the budget read."""

    is_liability: bool
    on_budget: bool
    #: Only read for an off-budget asset; carried everywhere so a shape is
    #: exactly what an account row holds.
    counts_as_savings: bool = True

    @property
    def is_card(self) -> bool:
        """An on-budget liability — the budget runs its card model on it."""
        return self.on_budget and self.is_liability


@dataclass(frozen=True)
class Move:
    kind: MoveKind
    #: The from-account of a transfer, or the one account of a transaction.
    account: AccountShape
    amount: Decimal
    category: CategoryKind = CategoryKind.NONE
    to_account: AccountShape | None = None
    direction: Direction | None = None

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError("a move's amount is a positive size; direction says which way")
        if self.kind is MoveKind.TRANSFER and (self.to_account is None or self.direction):
            raise ValueError("a transfer names a to-account and no direction")
        if self.kind is MoveKind.TRANSACTION and (self.to_account or self.direction is None):
            raise ValueError("a transaction names a direction and no to-account")


@dataclass(frozen=True)
class Leg:
    role: LegRole
    shape: AccountShape
    #: Signed as the row would be stored: negative leaves the account.
    amount: Decimal
    counterpart: AccountShape | None
    #: The category this leg carries — NONE unless the rule lets it carry one.
    category: CategoryKind


def category_role(move: Move) -> LegRole | None:
    """Which leg may carry the move's category, or None when neither may."""
    if move.kind is MoveKind.TRANSACTION:
        return LegRole.ACCOUNT if leg_may_carry_category(move.account.on_budget) else None
    assert move.to_account is not None
    if leg_may_carry_category(move.account.on_budget, move.to_account.on_budget):
        return LegRole.FROM
    if leg_may_carry_category(move.to_account.on_budget, move.account.on_budget):
        return LegRole.TO
    return None


def legs(move: Move) -> list[Leg]:
    """The rows this move would write, with the category on the leg allowed it."""
    carrier = category_role(move)

    def filed(role: LegRole) -> CategoryKind:
        return move.category if role is carrier else CategoryKind.NONE

    if move.kind is MoveKind.TRANSACTION:
        sign = 1 if move.direction is Direction.IN else -1
        return [
            Leg(
                LegRole.ACCOUNT,
                move.account,
                sign * move.amount,
                None,
                filed(LegRole.ACCOUNT),
            )
        ]
    assert move.to_account is not None
    return [
        Leg(LegRole.FROM, move.account, -move.amount, move.to_account, filed(LegRole.FROM)),
        Leg(LegRole.TO, move.to_account, move.amount, move.account, filed(LegRole.TO)),
    ]


_KIND_BY_TAG_INPUT = {field: CategoryKind(key) for field, key in TAG_INPUT_KEYS.items()}


def leg_facts(leg: Leg) -> LegFacts:
    """The booleans the classifier would read off this leg's row.

    Each counterpart fact is coalesced exactly as both column readers coalesce
    it when there is no counterpart: an asset, counting as savings.
    """
    cp = leg.counterpart
    return LegFacts(
        own_on_budget=leg.shape.on_budget,
        own_is_liability=leg.shape.is_liability,
        transfer_leg=cp is not None,
        tracked_counterpart=cp is not None and not cp.on_budget,
        counterpart_is_liability=cp is not None and cp.is_liability,
        counterpart_counts_as_savings=True if cp is None else cp.counts_as_savings,
        categorized=leg.category is not CategoryKind.NONE,
        in_system_group=leg.category is CategoryKind.INCOME,
        amount_positive=leg.amount > 0,
        **{field: leg.category is kind for field, kind in _KIND_BY_TAG_INPUT.items()},
    )


def _leg_terms(leg: Leg) -> dict[BudgetTerm, Decimal]:
    """Which budget figures one leg moves, under `ASSUMPTION`.

    Irreducible prose about `BudgetService` — see the module docstring for the
    differential test that holds it to the real arithmetic.
    """
    if not leg.shape.on_budget:
        # A tracking account contributes to no budget figure; its partner leg
        # (if on budget) says what the budget saw.
        return {}
    a = leg.amount
    filed = leg.category not in (CategoryKind.NONE, CategoryKind.INCOME)
    cp = leg.counterpart
    between_budget_accounts = cp is not None and cp.on_budget
    if leg.shape.is_card:
        if filed:
            # A funded swipe moves the money from the envelope to the card's
            # set-aside; a refund filed to the category moves it back.
            return {BudgetTerm.ENVELOPE: a, BudgetTerm.CARD_SET_ASIDE: -a}
        if between_budget_accounts and cp is not None and not cp.is_liability and a > 0:
            # A payment from cash spends the set-aside.
            return {BudgetTerm.CARD_SET_ASIDE: -a}
        if a < 0:
            # Owed with nothing set aside behind it.
            return {BudgetTerm.CARD_UNCOVERED: -a}
        # The card owed nothing, so it now holds a credit and no figure moves.
        return {}
    if filed:
        return {BudgetTerm.ENVELOPE: a}
    if between_budget_accounts:
        if cp is not None and cp.is_liability and a > 0:
            # A cash advance: real cash arrives, owed on the card as Uncovered.
            return {BudgetTerm.READY_TO_ASSIGN: a}
        # Between two cash accounts, or the cash side of a card payment,
        # whose set-aside was already out of Ready to Assign.
        return {}
    return {BudgetTerm.READY_TO_ASSIGN: a}


def budget_terms(move: Move) -> dict[BudgetTerm, Decimal]:
    """The budget figures a move changes and by how much, zeros dropped."""
    total: dict[BudgetTerm, Decimal] = {}
    for leg in legs(move):
        for term, delta in _leg_terms(leg).items():
            total[term] = total.get(term, Decimal("0")) + delta
    return {term: delta for term, delta in total.items() if delta != 0}


def report_families(cls: ActivityClass) -> list[ReportFamily]:
    """The report families whose class tuple holds this class."""
    return [family for family, classes in REPORT_FAMILY_CLASSES.items() if cls in classes]


def counts_as_planned_spend_by_tag(leg: Leg, cls: ActivityClass) -> bool:
    """Whether plan reports count this leg as spent through
    `PLANNED_SPEND_TAG_KEYS` although its class is not spending — the savings
    tag's outflow, which Budget vs Actual holds against the plan.

    Stated as the policy's exception only: an on-budget categorized outflow
    (`PLANNED_SPEND_ROW`'s shape) whose category kind is one of those tags.
    """
    return (
        leg.shape.on_budget
        and leg.amount < 0
        and leg.category.value in TAG_INPUT_KEYS.values()
        and leg.category.value in PLANNED_SPEND_TAG_KEYS
        and cls not in SPENDING_CLASSES
    )


@dataclass(frozen=True)
class LegExplanation:
    role: LegRole
    on_budget: bool
    amount: Decimal
    category: CategoryKind
    cls: ActivityClass
    reason: ActivityReason
    #: Empty for an off-budget leg: every report here is on-budget scoped.
    counted_in: list[ReportFamily]
    planned_spend_by_tag: bool


@dataclass(frozen=True)
class Figures:
    """The report figures a set of legs adds up to."""

    income: Decimal
    spending: Decimal
    cost_of_living: Decimal
    savings: Decimal
    debt_principal: Decimal
    savings_rate: float | None
    savings_rate_with_debt: float | None


def _family_total(buckets: Mapping[str, Decimal], family: ReportFamily) -> Decimal:
    classes = REPORT_FAMILY_CLASSES[family]
    if family is ReportFamily.INCOME:
        return sum((buckets.get(c.value, Decimal("0")) for c in classes), Decimal("0"))
    return sum((class_magnitude(buckets, c) for c in classes), Decimal("0"))


def figures(buckets: Mapping[str, Decimal]) -> Figures:
    """Report figures from class buckets, through the report's own division."""
    rates = savings_rates(buckets)
    return Figures(
        income=_family_total(buckets, ReportFamily.INCOME),
        spending=_family_total(buckets, ReportFamily.SPENDING),
        cost_of_living=_family_total(buckets, ReportFamily.COST_OF_LIVING),
        savings=class_magnitude(buckets, ActivityClass.SAVINGS),
        debt_principal=class_magnitude(buckets, ActivityClass.DEBT_PRINCIPAL),
        savings_rate=rates["savings_rate"],
        savings_rate_with_debt=rates["savings_rate_with_debt"],
    )


@dataclass(frozen=True)
class MoveExplanation:
    category_role: LegRole | None
    #: False when a category was asked for and no leg may carry it.
    category_applied: bool
    legs: list[LegExplanation]
    budget_terms: dict[BudgetTerm, Decimal]
    #: Signed class sums over the on-budget legs — what the reports aggregate.
    class_totals: dict[str, Decimal] = field(default_factory=dict)
    net_worth_delta: Decimal = Decimal("0")


def explain_move(
    move: Move, classes: Sequence[tuple[ActivityClass, ActivityReason]]
) -> MoveExplanation:
    """Compose the answer for one move from its legs' classes.

    `classes` is aligned with `legs(move)` and comes from the classifier —
    this function never decides a class.
    """
    move_legs = legs(move)
    if len(classes) != len(move_legs):
        raise ValueError("one (class, reason) per leg")
    explained: list[LegExplanation] = []
    totals: dict[str, Decimal] = {}
    for leg, (cls, reason) in zip(move_legs, classes, strict=True):
        if leg.shape.on_budget:
            totals[cls.value] = totals.get(cls.value, Decimal("0")) + leg.amount
        explained.append(
            LegExplanation(
                role=leg.role,
                on_budget=leg.shape.on_budget,
                amount=leg.amount,
                category=leg.category,
                cls=cls,
                reason=reason,
                counted_in=report_families(cls) if leg.shape.on_budget else [],
                planned_spend_by_tag=counts_as_planned_spend_by_tag(leg, cls),
            )
        )
    role = category_role(move)
    return MoveExplanation(
        category_role=role,
        category_applied=move.category is CategoryKind.NONE or role is not None,
        legs=explained,
        budget_terms=budget_terms(move),
        class_totals=totals,
        # A liability's balance is stored negative, so assets minus debts is
        # the plain sum: a transfer nets to zero, a transaction moves it.
        net_worth_delta=sum((leg.amount for leg in move_legs), Decimal("0")),
    )


def month_buckets(explanations: Sequence[MoveExplanation]) -> dict[str, Decimal]:
    """Class totals across several moves."""
    total: dict[str, Decimal] = {}
    for explanation in explanations:
        for cls, amount in explanation.class_totals.items():
            total[cls] = total.get(cls, Decimal("0")) + amount
    return total


# ─── Account shapes, for the account-type explainer ──────────────────────────

_CASH = AccountShape(is_liability=False, on_budget=True)
_EXAMPLE = Decimal("1000")


@dataclass(frozen=True)
class ShapeExample:
    description: str
    move: Move


@dataclass(frozen=True)
class ShapeInfo:
    key: str
    label: str
    is_liability: bool
    on_budget: bool
    #: None where the flag changes nothing: on budget, or a liability.
    counts_as_savings: bool | None
    money_in: ShapeExample
    money_out: ShapeExample


def _transfer(frm: AccountShape, to: AccountShape) -> Move:
    return Move(MoveKind.TRANSFER, frm, _EXAMPLE, to_account=to)


def _transaction(
    account: AccountShape, direction: Direction, category: CategoryKind = CategoryKind.NONE
) -> Move:
    return Move(MoveKind.TRANSACTION, account, _EXAMPLE, category, direction=direction)


def _shapes() -> list[ShapeInfo]:
    card = AccountShape(is_liability=True, on_budget=True)
    saving = AccountShape(is_liability=False, on_budget=False, counts_as_savings=True)
    keeping = AccountShape(is_liability=False, on_budget=False, counts_as_savings=False)
    debt = AccountShape(is_liability=True, on_budget=False)
    return [
        ShapeInfo(
            "budget_cash",
            "Budget account",
            False,
            True,
            None,
            ShapeExample(
                "Money arriving with no category, like a paycheck",
                _transaction(_CASH, Direction.IN),
            ),
            ShapeExample(
                "A purchase filed to a category",
                _transaction(_CASH, Direction.OUT, CategoryKind.ORDINARY),
            ),
        ),
        ShapeInfo(
            "budget_card",
            "Credit card",
            True,
            True,
            None,
            ShapeExample("A payment from a budget account", _transfer(_CASH, card)),
            ShapeExample(
                "A purchase filed to a category",
                _transaction(card, Direction.OUT, CategoryKind.ORDINARY),
            ),
        ),
        ShapeInfo(
            "tracked_savings",
            "Tracked account that counts as savings",
            False,
            False,
            True,
            ShapeExample("A transfer from a budget account", _transfer(_CASH, saving)),
            ShapeExample("A transfer back to a budget account", _transfer(saving, _CASH)),
        ),
        ShapeInfo(
            "tracked_asset",
            "Tracked account that does not count as savings",
            False,
            False,
            False,
            ShapeExample("Buying it from a budget account", _transfer(_CASH, keeping)),
            ShapeExample("Selling it into a budget account", _transfer(keeping, _CASH)),
        ),
        ShapeInfo(
            "tracked_debt",
            "Tracked loan",
            True,
            False,
            None,
            ShapeExample("A payment from a budget account", _transfer(_CASH, debt)),
            ShapeExample("Borrowing into a budget account", _transfer(debt, _CASH)),
        ),
    ]


#: One per account shape a type can have. Custom types land on one of these by
#: their three facts, so they are explained without an entry of their own.
SHAPES: list[ShapeInfo] = _shapes()
