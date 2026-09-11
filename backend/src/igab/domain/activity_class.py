"""What a transaction row *means* in money terms, as one SQL expression.

Every report that talks about spending, income or saving has to agree on this,
so it lives in one place and is derived rather than stored: a stored column
would need a backfill and would go stale the moment a category is retagged or
an account changes type.

The classes form a **total partition** — every posted leaf row falls into
exactly one, and the classes sum back to the account delta. That property is
asserted in tests/integration/invariants.py, and it is the point: the
`CASH_FLOW_ROW` bug happened because "not cash flow" was a leftover bucket
rather than a named class, so rows could fall through it unnoticed.

Scope note: a row's class is read from its category, which lives on split
*children*. Apply this to LEAF queries. A split parent has no category and can
legitimately mix classes across its legs (groceries and a savings transfer in
one bank row), so ACTIVITY_CLASS on a parent row is a fall-through, not an
answer. Where one parent row is shown with a class — the Timeline, the
transaction editor's "Counts as" line — its class is rolled up from its legs by
`split_leg_classes` and `rolled_up_classes` below. PARENT_ROW aggregates do not
use the roll-up: a sum splits per class by reading the legs themselves.

The rules are ordered and first-match-wins, so each one also carries a stable
`ActivityReason`. That is what lets the UI answer "why is this savings?" with
"transfer to an off-budget asset account" instead of asking the user to trust
an opaque reclassification.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import Select, and_, case, func, literal, not_, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from igab.db.models import (
    Account,
    Payee,
    Transaction,
)
from igab.repositories.category_filters import IN_SYSTEM_GROUP
from igab.repositories.txn_filters import (
    CASH_FLOW_ROW,
    COST_OF_LIVING_TAGGED,
    COUNTERPART_ACCOUNT_ID,
    COUNTERPART_OFF_BUDGET,
    ESSENTIAL_TAGGED,
    LEAF,
    NOT_DELETED,
    POSTED,
    TRANSFER_LEG,
    category_tagged,
    row_category,
)


class ActivityClass(StrEnum):
    """What a row does to the budget. Ordered roughly money-in to money-out."""

    INCOME = "income"
    SPENDING = "spending"
    SAVINGS = "savings"
    DEBT_PRINCIPAL = "debt_principal"
    #: Money moved between two accounts we track. Neutral: never income or
    #: expense. Named rather than filtered out, so the partition stays total.
    TRANSFER_INTERNAL = "transfer_internal"
    #: Growth (or loss) inside a tracked asset — dividends, market movement,
    #: employer contributions. Emphatically NOT saving: counting market growth
    #: as saving would make a savings rate meaningless.
    INVESTMENT_RETURN = "investment_return"
    #: Interest and fees accruing on a tracked debt. Distinct from
    #: DEBT_PRINCIPAL: interest is a real cost, principal is net-worth neutral.
    DEBT_INTEREST = "debt_interest"
    #: An account's starting balance. Never income — it is where counting
    #: begins. RESERVED: nothing emits this yet, because the importer does not
    #: mark starting-balance rows. See the Phase 0b note in the plan.
    OPENING_BALANCE = "opening_balance"


class ActivityReason(StrEnum):
    """Which rule decided the class. User-facing — keep these stable."""

    TAGGED_SAVINGS = "tagged_savings"
    TAGGED_DEBT = "tagged_debt"
    TRANSFER_TO_TRACKED_ASSET = "transfer_to_tracked_asset"
    TRANSFER_TO_TRACKED_DEBT = "transfer_to_tracked_debt"
    INTERNAL_TRANSFER = "internal_transfer"
    TRACKED_ASSET_ACTIVITY = "tracked_asset_activity"
    TRACKED_DEBT_ACTIVITY = "tracked_debt_activity"
    UNCATEGORIZED_INFLOW = "uncategorized_inflow"
    DEFAULT_SPENDING = "default_spending"


#: Human-readable copy for each reason, shown wherever a row's class is
#: explained. Kept next to the rules so the two cannot drift apart.
REASON_TEXT: dict[ActivityReason, str] = {
    ActivityReason.TAGGED_SAVINGS: "its category is tagged as savings",
    ActivityReason.TAGGED_DEBT: "its category is tagged as debt principal",
    ActivityReason.TRANSFER_TO_TRACKED_ASSET: (
        "it moves money to a tracked account you own, so it builds savings rather than spending it"
    ),
    ActivityReason.TRANSFER_TO_TRACKED_DEBT: (
        "it pays down a tracked debt, which changes what you owe rather than what you spend"
    ),
    ActivityReason.INTERNAL_TRANSFER: "it moves money between two of your own accounts",
    ActivityReason.TRACKED_ASSET_ACTIVITY: (
        "it happened inside a tracked account — growth or loss, not money you budgeted"
    ),
    ActivityReason.TRACKED_DEBT_ACTIVITY: (
        "it happened inside a tracked debt — interest or fees, not money you budgeted"
    ),
    ActivityReason.UNCATEGORIZED_INFLOW: "it is money arriving with no category, ready to assign",
    ActivityReason.DEFAULT_SPENDING: "it is ordinary spending from a budget account",
}

#: Short label for each class, for anywhere a class is shown to a person.
CLASS_LABEL: dict[ActivityClass, str] = {
    ActivityClass.INCOME: "Income",
    ActivityClass.SPENDING: "Spending",
    ActivityClass.SAVINGS: "Savings",
    ActivityClass.DEBT_PRINCIPAL: "Debt payment",
    ActivityClass.TRANSFER_INTERNAL: "Transfer",
    ActivityClass.INVESTMENT_RETURN: "Investment change",
    ActivityClass.DEBT_INTEREST: "Interest & fees",
    ActivityClass.OPENING_BALANCE: "Starting balance",
}

_LIABILITY = "liability"


def _account_field(account_id, column):
    return select(column).where(Account.id == account_id).correlate(Transaction).scalar_subquery()


_own_on_budget = _account_field(Transaction.account_id, Account.on_budget)

#: The row's own account always resolves — `account_id` is NOT NULL behind an
#: FK — and `classification` is NOT NULL since b8c3e5a71f42, so this is plainly
#: two-valued. It used to be coalesced against pre-registry rows; that state no
#: longer exists.
_own_is_liability = _account_field(Transaction.account_id, Account.classification) == _LIABILITY

#: The counterpart is read through a subquery that yields NULL when nothing
#: resolves, whatever constraint the column carries — and an uncoalesced
#: comparison would then be UNKNOWN, declining BOTH the asset arm and the
#: liability arm below and dropping a transfer to the spending default.
#:
#: Two things currently make that unreachable, and neither is local to this
#: file: `transfer_id` is an FK with ondelete=SET NULL, so a hard-deleted
#: partner unlinks the leg rather than leaving it dangling; and the arms are
#: guarded by `_TRACKED_COUNTERPART`, which is false when nothing resolves.
#: The coalesce is kept because that is a four-step argument across three
#: modules, and it costs nothing to make the expression two-valued by
#: construction instead. `test_activity_class_matrix.py` pins the FK half.
_counterpart_is_liability = (
    func.coalesce(_account_field(COUNTERPART_ACCOUNT_ID, Account.classification), "asset")
    == _LIABILITY
)


# The category-tag predicate lives in txn_filters (category_tagged) — the
# essentials report needs the same shape, and one SQL spelling is the rule.
_tagged = category_tagged


#: Inflow categories (YNAB's "Ready to Assign"). A categorized inflow to an
#: ordinary category is a refund, which nets against that category's spending —
#: calling it income would double-count it and inflate a savings rate's
#: denominator.
#:
#: The rule itself lives in `category_filters.IN_SYSTEM_GROUP` and is lifted
#: onto the row by `txn_filters.row_category` — the same lift the reserve
#: identity's unbudgeted-credit term uses. It was spelled out here as a second
#: `category_id IN (...)` subquery, which also needed its own NULL guard; the
#: EXISTS form is two-valued and does not.
_IN_SYSTEM_GROUP = row_category(IN_SYSTEM_GROUP)

_CATEGORIZED = Transaction.category_id.isnot(None)
_TRACKED_COUNTERPART = COUNTERPART_OFF_BUDGET


@dataclass(frozen=True)
class _Inputs:
    """Where the rules read the columns they cannot get from `transactions`.

    The rules below are written once against this, so the two ways of reaching
    those columns — correlated subqueries and LEFT JOINs — cannot drift into
    disagreeing about *what* the rules are. All a differential test then has to
    prove is that the two ways of reading a column agree, which is a far
    smaller claim than "these two rule sets behave identically".
    """

    # `Any` because the two implementations supply genuinely different types
    # for the same thing — a mapped column attribute on one side, a built SQL
    # expression on the other — and they share no common supertype narrower
    # than this. What matters is that both answer the boolean operators the
    # rules apply to them, which the differential test verifies for real.
    own_on_budget: Any
    own_is_liability: Any
    counterpart_is_liability: Any
    tracked_counterpart: Any
    transfer_leg: Any


Rule = tuple[ColumnElement[bool], ActivityClass, ActivityReason]


def _rules(c: _Inputs) -> list[Rule]:
    """(condition, class, reason) in priority order. Tags come first so a
    user's explicit statement always beats an inferred one."""
    return [
        # `savings` only. `long_term_expense` used to ride along here, and it
        # inverted the sign of the one event in a sinking fund that is
        # unambiguously a cost.
        #
        # A sinking fund's monthly set-aside is a BudgetAssignment — a budget
        # row, not a transaction — so there is nothing for a classifier to
        # protect from being counted as spending. The only transaction the
        # envelope ever sees is the payout: the property-tax bill, the annual
        # insurance premium. Tagging that SAVINGS said the household saved
        # $2,340 in the month it paid its property tax, kept the bill out of
        # every spending report, out of Cost of Living and out of the
        # emergency-fund target, and left `budget_vs_actual` counting the
        # envelope's assignments but not its spending — a permanent phantom
        # underspend on Plan vs Reality.
        #
        # Nothing is lost by dropping it. A transfer from the envelope to a
        # tracked savings account still classes SAVINGS by rule 3 below, which
        # asks where the money went rather than what the category is called.
        # The Savings report is unaffected: it reads the tag and the
        # assignment rows, never the class.
        #
        # `savings` stays, because that behaviour was asked for directly — see
        # `ReportService.savings_rate`. Tagging an envelope Savings means its
        # outflows count as saving even with no transfer, which is a different
        # claim from "this envelope holds money for a known future bill".
        (_tagged("savings"), ActivityClass.SAVINGS, ActivityReason.TAGGED_SAVINGS),
        (_tagged("debt_principal"), ActivityClass.DEBT_PRINCIPAL, ActivityReason.TAGGED_DEBT),
        # Where the money went decides the class, not whether the user bothered to
        # categorize it. An uncategorized transfer to a brokerage is still saving:
        # it leaves the budget and stays in net worth. Requiring a category here
        # meant those legs fell to the neutral bucket below and vanished from the
        # savings rate — and YNAB exports are full of uncategorized
        # tracking-account transfers.
        (
            and_(c.transfer_leg, c.tracked_counterpart, ~c.counterpart_is_liability),
            ActivityClass.SAVINGS,
            ActivityReason.TRANSFER_TO_TRACKED_ASSET,
        ),
        (
            and_(c.transfer_leg, c.tracked_counterpart, c.counterpart_is_liability),
            ActivityClass.DEBT_PRINCIPAL,
            ActivityReason.TRANSFER_TO_TRACKED_DEBT,
        ),
        # What remains is movement between two on-budget accounts (both legs sit
        # inside the budget, so counting either double-counts), or a leg whose
        # counterpart could not be resolved. A CATEGORIZED unresolvable leg falls
        # past this to the spending rules — it keeps the meaning its category gives
        # it rather than disappearing into a neutral bucket.
        (
            and_(c.transfer_leg, ~_CATEGORIZED),
            ActivityClass.TRANSFER_INTERNAL,
            ActivityReason.INTERNAL_TRANSFER,
        ),
        (
            and_(c.own_on_budget == False, ~c.own_is_liability),  # noqa: E712
            ActivityClass.INVESTMENT_RETURN,
            ActivityReason.TRACKED_ASSET_ACTIVITY,
        ),
        (
            and_(c.own_on_budget == False, c.own_is_liability),  # noqa: E712
            ActivityClass.DEBT_INTEREST,
            ActivityReason.TRACKED_DEBT_ACTIVITY,
        ),
        # An inflow category is income whichever way the money moved: a reversed or
        # clawed-back paycheck is negative income, not spending. Sign still decides
        # for UNcategorized rows, where it is the only signal available.
        (
            or_(and_(Transaction.amount > 0, ~_CATEGORIZED), _IN_SYSTEM_GROUP),
            ActivityClass.INCOME,
            ActivityReason.UNCATEGORIZED_INFLOW,
        ),
    ]


#: How the shipped expression reaches those columns: correlated subqueries,
#: evaluated per row.
_SUBQUERY_INPUTS = _Inputs(
    own_on_budget=_own_on_budget,
    own_is_liability=_own_is_liability,
    counterpart_is_liability=_counterpart_is_liability,
    tracked_counterpart=_TRACKED_COUNTERPART,
    transfer_leg=TRANSFER_LEG,
)


# ─── The same rules, reading joined columns ──────────────────────────────────
#
# Every join below is to a primary key, so each matches at most once and the
# result stays one row per transaction. That is load-bearing rather than
# incidental: a join matching twice would multiply every total computed through
# the expression while still looking like a number. `class_agreement.py` checks
# it directly, and `assert_activity_class_partition` checks it at 48 more sites.

_own_acct = aliased(Account, name="own_acct")
_partner_txn = aliased(Transaction, name="partner_txn")
_transfer_payee = aliased(Payee, name="xfer_payee")
_counterpart_acct = aliased(Account, name="counterpart_acct")

#: The counterpart account id, joined rather than looked up twice per row. Same
#: precedence as COUNTERPART_ACCOUNT_ID: the partner link is the strong signal,
#: an orphaned leg falls back to the account its transfer payee names.
_joined_counterpart_id = func.coalesce(_partner_txn.account_id, _transfer_payee.transfer_account_id)

#: NULL when the join found nothing, which is the same three-valued hazard the
#: subquery version documents — so both ends are coalesced identically. An
#: unresolvable counterpart reads as on-budget (so not "tracked") and as an
#: asset, exactly as before.
_joined_counterpart_on_budget = func.coalesce(_counterpart_acct.on_budget, True)

_JOINED_INPUTS = _Inputs(
    own_on_budget=_own_acct.on_budget,
    own_is_liability=_own_acct.classification == _LIABILITY,
    counterpart_is_liability=(
        func.coalesce(_counterpart_acct.classification, "asset") == _LIABILITY
    ),
    tracked_counterpart=not_(_joined_counterpart_on_budget),
    # `transfer_account_id IS NOT NULL` on the joined payee is exactly what the
    # TRANSFER_PAYEE EXISTS asks, and is two-valued for the same reason.
    transfer_leg=or_(
        Transaction.transfer_id.isnot(None),
        _transfer_payee.transfer_account_id.isnot(None),
    ),
)

#: The shipped rules, reading joined columns.
RULES: list[Rule] = _rules(_JOINED_INPUTS)


def apply_class_joins(stmt: Select) -> Select:
    """Bring in the columns ACTIVITY_CLASS reads.

    Must be applied to any query that selects, filters or groups by the class
    or reason expressions. Forgetting leaves the aliased tables unjoined in the
    FROM, which is a cartesian product: SQLAlchemy warns, and pyproject
    promotes that warning to an error so it fails a test rather than inflating
    a total.

    The statement must already be anchored on `transactions` — selecting at
    least one Transaction column, or having it as the explicit FROM — since
    these joins chain from it. Every consumer does; a query that selected only
    the CASE would not, which is a real way to get a cartesian product while
    doing everything else right.
    """
    return (
        stmt.outerjoin(_own_acct, _own_acct.id == Transaction.account_id)
        .outerjoin(_partner_txn, _partner_txn.id == Transaction.transfer_id)
        .outerjoin(_transfer_payee, _transfer_payee.id == Transaction.payee_id)
        .outerjoin(_counterpart_acct, _counterpart_acct.id == _joined_counterpart_id)
    )


#: The class of a transaction row. Use in select(), group_by() and where() —
#: and apply CLASS_JOINS to the same query, or the aliased tables it reads land
#: in the FROM unjoined and every total multiplies.
ACTIVITY_CLASS = case(
    *[(condition, literal(cls.value)) for condition, cls, _ in RULES],
    else_=literal(ActivityClass.SPENDING.value),
)

#: Which rule fired, for explaining a row to the user.
ACTIVITY_REASON = case(
    *[(condition, literal(reason.value)) for condition, _, reason in RULES],
    else_=literal(ActivityReason.DEFAULT_SPENDING.value),
)

#: Joins a query must apply before it can use the expressions above.
#:
#: A separate symbol rather than something callers just remember, because one
#: caller cannot remember: `tests/integration/invariants.py` asserts that the
#: classes partition every posted leaf row, and it counts rows to do it — which
#: is exactly the check that catches a join matching more than once. That check
#: is only worth anything if it builds its query the way the reports build
#: theirs, and it has no other way to know how they do. Reading this keeps the
#: two in step across all 48 of its call sites.
CLASS_JOINS: Callable[[Select], Select] | None = apply_class_joins

#: A row that is income: what Income by Source and both Cash Flow Sankey modes
#: count, and the same class Income vs Expenses reads from its partition.
#: Apply `apply_class_joins` with it. Account scope stays the caller's —
#: on-budget by default, or the user's explicit selection.
#:
#: **The class decides, never the sign.** Budgeted-mode Sankey summed
#: `amount > 0` split parents, so a 3,000 paycheque and a 400 clawback read
#: 3,000 there and 2,600 everywhere else, and flipping the Sankey between its
#: modes changed "Income" although the mode is about spending. A refund or a
#: brokerage withdrawal counted as income too. LEAF rather than PARENT_ROW
#: because a split parent carries no category and so no class of its own.
INCOME_ROW = and_(
    NOT_DELETED,
    POSTED,
    LEAF,
    CASH_FLOW_ROW,
    ACTIVITY_CLASS == ActivityClass.INCOME.value,
)


# ─── The previous implementation, kept as a test oracle ──────────────────────
#
# Correlated scalar subqueries: the same rules reading the same columns, one
# lookup per row per rule. Replaced because the CASE short-circuits, so the
# common row — ordinary spending, matching no rule — fell through every arm and
# paid the maximum number of subplan executions. Over a 41k-row register a
# three-year monthly aggregate cost 342 ms against 13 ms for the joined form.
#
# Kept, and only ever imported by tests, because it is the thing that makes the
# joined version checkable: `tests/integration/class_agreement.py` requires the
# two to classify every row of a realistic budget identically, class and reason
# both. Delete this and that test has nothing left to compare against.

RULES_SUBQUERY: list[Rule] = _rules(_SUBQUERY_INPUTS)

ACTIVITY_CLASS_SUBQUERY = case(
    *[(condition, literal(cls.value)) for condition, cls, _ in RULES_SUBQUERY],
    else_=literal(ActivityClass.SPENDING.value),
)

ACTIVITY_REASON_SUBQUERY = case(
    *[(condition, literal(reason.value)) for condition, _, reason in RULES_SUBQUERY],
    else_=literal(ActivityReason.DEFAULT_SPENDING.value),
)


#: The classes a spending report means by "spending" — everything a household
#: would call money going out, and nothing that merely moves or grows it.
SPENDING_CLASSES = (ActivityClass.SPENDING,)
#: Money that left the budget but stayed in the household's net worth.
SAVINGS_CLASSES = (ActivityClass.SAVINGS, ActivityClass.DEBT_PRINCIPAL)

#: What "a month costs to run" means: spending, plus the cash side of a payment
#: into a tracked debt. Read by the Essentials report, Cost of Living, the
#: Overview card and the Guide's emergency-fund target — one tuple, because a
#: category counted in one of those must be counted in all of them.
#:
#: Deliberately NOT `SPENDING_CLASSES`. A spending report is right to leave
#: DEBT_PRINCIPAL out: paying down principal moves net worth between columns
#: rather than consuming it. But a household that stops paying its mortgage
#: does not keep its house, so the payment is a cost of living whether or not
#: it also buys equity — and until this existed, tagging a mortgage Essential
#: did nothing at all, silently, because the payment classes DEBT_PRINCIPAL.
#:
#: DEBT_INTEREST is absent on purpose, and adding it would be theatre: the
#: rules above only ever emit it on an OFF-budget liability account, which
#: every reader here excludes with ON_BUDGET_ACCOUNT. The cash-side transfer is
#: the whole payment anyway — principal, interest and escrow together — which
#: is the figure someone means by "my mortgage is $3,000".
#:
#: The divergence from SPENDING_CLASSES is pinned by
#: tests/integration/test_essentials_count_debt_payments.py, which fails if the
#: two are ever made equal.
COST_OF_LIVING_CLASSES = (ActivityClass.SPENDING, ActivityClass.DEBT_PRINCIPAL)

#: Everything that left the budget: spending, plus the money that merely moved
#: or grew. This is what a spending report means when the reader opts in to the
#: fuller picture — "where did it all go", rather than "what did I consume".
#:
#: Named here rather than built at each call site because it now has two: the
#: reports router's `include_savings` flag and the chat's spending tool. Two
#: places assembling the same tuple is how the badge and the register came to
#: disagree.
SPENDING_WITH_SAVINGS_CLASSES = SPENDING_CLASSES + SAVINGS_CLASSES


def explain(reason: str) -> str:
    """Prose for a reason code, safe for an unknown value from an older row."""
    if reason in SPLIT_REASON_TEXT:
        return SPLIT_REASON_TEXT[reason]
    try:
        return REASON_TEXT[ActivityReason(reason)]
    except (ValueError, KeyError):
        return "it did not match any specific rule"


# ─── Split parents ───────────────────────────────────────────────────────────
#
# One home for "what does this split count as", because two places show a
# split parent with a class. The Timeline rolled the legs up and the editor's
# classification endpoint did not, so an all-savings split was a Savings dot on
# the Timeline and "ordinary spending from a budget account" in the editor.

#: The label of a split whose legs do not share one class. Served, never
#: guessed at: falling back to the amount's sign is the mislabelling this
#: taxonomy exists to end.
SPLIT_LABEL = "Split"

#: Reason codes for a split parent. Not `ActivityReason` members: no SQL rule
#: emits them, and every member of that enum must fire on a leaf row.
SPLIT_REASON_TEXT: dict[str, str] = {
    "split_legs_agree": "every line of the split counts this way",
    "split_legs_differ": "its lines count in different ways, and each is counted on its own",
}


def split_leg_classes(parent_ids: Sequence[Any]) -> Select:
    """`(parent id, class)` for every live leg of these split parents.

    One query for a page of parents rather than one per row. Live legs only:
    editing or undoing a split soft-deletes its old legs and leaves them
    pointing at the parent.
    """
    return apply_class_joins(
        select(Transaction.parent_transaction_id, ACTIVITY_CLASS.label("cls")).where(
            Transaction.parent_transaction_id.in_(parent_ids), NOT_DELETED
        )
    )


def rolled_up_classes(leg_rows) -> dict[Any, str | None]:
    """{parent id: its class} from `split_leg_classes` rows.

    One distinct class among the legs IS the parent's class. Anything else is
    honestly mixed, and the answer is None — shown as `SPLIT_LABEL`. A parent
    with no live legs is absent, which reads the same.
    """
    found: dict[Any, set[str]] = {}
    for parent_id, cls in leg_rows:
        found.setdefault(parent_id, set()).add(cls)
    return {pid: next(iter(c)) if len(c) == 1 else None for pid, c in found.items()}


def class_label(cls: str | None) -> str:
    """The display label for a class, or `SPLIT_LABEL` for a mixed split."""
    return SPLIT_LABEL if cls is None else CLASS_LABEL[ActivityClass(cls)]


def split_reason(cls: str | None) -> str:
    """The reason code for a split parent whose rolled-up class is `cls`."""
    return "split_legs_differ" if cls is None else "split_legs_agree"


def counted_classes(
    include: Sequence[ActivityClass] | None = None, *, scoped_accounts: bool = False
) -> set[str]:
    """The class VALUES a spending rollup counts — the one statement of the
    class set and its widening. `counted_class_filter` is the same set as a
    WHERE clause; there is no third spelling.

    Defaults to spending alone. A transfer to a brokerage or a mortgage is
    money leaving the budget, but it is not money spent, and counting it as
    spending skews every average. Callers that want the wider picture pass
    the classes they mean.

    `scoped_accounts` says the user made an explicit account selection —
    `txn_filters.account_scope` returns it — which overrides the on-budget
    default, so they may be looking straight at a tracked account, whose
    outflows classify `investment_return` (brokerage fees) or `debt_interest`
    (loan interest) and never `spending`. Without widening, picking
    "Brokerage" in the account filter drew an empty chart.

    The widening was written three times and the third copy did not have it,
    so a tracked account drew nothing on Spending Trends beside a populated
    Pareto. Then the predicate form lived in services beside this set, kept
    in step by a docstring cross-reference, and read by the Breakdown and
    Payee Analysis while three other rollups read this.
    """
    values = {c.value for c in (include or SPENDING_CLASSES)}
    if scoped_accounts:
        values |= {ActivityClass.INVESTMENT_RETURN.value, ActivityClass.DEBT_INTEREST.value}
    return values


def counted_class_filter(
    include: Sequence[ActivityClass] | None = None, *, scoped_accounts: bool = False
) -> ColumnElement[bool]:
    """`counted_classes` as a WHERE clause, for a query that filters on the
    class rather than selecting it.

    The caller must also apply `apply_class_joins`. This is the one place the
    class is used without the joins visibly beside it, and a query with the
    predicate and no joins is a cartesian product — which `pyproject.toml`
    promotes from a warning to a test failure.
    """
    return ACTIVITY_CLASS.in_(sorted(counted_classes(include, scoped_accounts=scoped_accounts)))


# ─── Necessity tiers ─────────────────────────────────────────────────────────
#
# Two nested sets, from a design conversation with the household's second user:
#
#   "cost of living would be anything that comes out of my account on a monthly
#    basis that's not discretionary, like utilities, mortgage payment, any debt
#    payments, subscriptions, etc. essentials would only be the things that are
#    100% necessary, so mortgage payment is in there but subscriptions aren't...
#    seeing a report that shows the difference in those two could be a good way
#    to identify areas to cut back and save on or things to shed in some kind
#    of emergency event"
#
# The GAP is the product. Before this, both reports read one tag and one class
# tuple — Cost of Living was the Essentials table rolled up by group, and its
# own docstring said so ("Nothing new is queried... Only the rollup is new").
# The only difference a user could see between the two screens was a calendar
# artifact from three different windows.
#
# **The nesting is structural, not asserted.** The wider predicate contains the
# narrower one as a disjunct, so Essentials ⊆ Cost of Living cannot drift and
# needs no invariant policing it. An invariant that can only be satisfied is
# decoration; this is the mechanism instead.
#
# The class tuple stays shared. `COST_OF_LIVING_CLASSES` answers what a row
# does to net worth, which is the same question for both tiers — the tiers
# differ in MEMBERSHIP, not in class. Expressing the nesting as a second class
# tuple would fight `TestTheDivergenceIsDeliberate` for no gain.


class NecessityTier(StrEnum):
    """Which necessity question a figure answers."""

    #: What a household could not cut. Sizes the emergency fund, so it stays
    #: the lean figure — see the deliberate divergence pinned in
    #: `tests/integration/test_necessity_tiers.py`.
    ESSENTIAL = "essential"
    #: Everything non-discretionary. Essentials plus the committed-but-sheddable,
    #: plus debt principal by class.
    COST_OF_LIVING = "cost_of_living"


def tier_keys(tier: NecessityTier) -> list[str]:
    """The system tag keys whose membership this tier reads.

    Kept beside `tier_scope` so a tier cannot be given a predicate and a tag
    set that disagree — the applied-count and the WHERE clause have to ask
    about the same tags, and they did not: the count included payee tags long
    after the predicate stopped reading them.
    """
    if tier is NecessityTier.ESSENTIAL:
        return ["essential"]
    return ["essential", "cost_of_living"]


def basis_is_chosen(basis: str) -> bool:
    """Whether a necessity figure was measured over what the household chose —
    categories bound in the Guide ("bound") or its tags ("tag") — rather than
    the "all" fallback `_necessity_scope` returns when nothing is chosen.

    "all" is every category: the burn rate. Quoted as Essentials it says the
    household could not cut a single thing, and it fired "what you could not
    cut costs more than you take home" on spending that could be cut. A
    figure on that basis is unknown, not everything. Said once, here: the
    Essentials headline, both Cost of Living tiers and its notes all read it,
    and they had three spellings of it.
    """
    return basis != "all"


def tier_scope(tier: NecessityTier):
    """The membership predicate for one tier.

    Debt principal enters Cost of Living by CLASS rather than by tag, which is
    what delivers "any debt payments" without asking a household to tag each
    loan envelope. **Payments only**: the class also marks money coming IN
    from a tracked loan — a disbursement, a HELOC draw — and that netted
    against the tier, so $5,000 of loan proceeds read as a negative cost of
    living and a "comfortable" standing for a whole year. The tag arms keep
    netting refunds, as a category's own activity does.
    """
    if tier is NecessityTier.ESSENTIAL:
        return ESSENTIAL_TAGGED
    return or_(
        ESSENTIAL_TAGGED,
        COST_OF_LIVING_TAGGED,
        and_(ACTIVITY_CLASS == ActivityClass.DEBT_PRINCIPAL.value, Transaction.amount < 0),
    )
