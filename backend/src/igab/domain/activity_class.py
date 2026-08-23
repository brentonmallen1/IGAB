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
one bank row), so PARENT_ROW aggregates — account balances, cash flow — cannot
use it as-is and still classify by amount sign. Splitting those correctly means
rolling children up per class, which is not done here.

The rules are ordered and first-match-wins, so each one also carries a stable
`ActivityReason`. That is what lets the UI answer "why is this savings?" with
"transfer to an off-budget asset account" instead of asking the user to trust
an opaque reclassification.
"""

from collections.abc import Callable
from enum import StrEnum

from sqlalchemy import Select, and_, case, func, literal, or_, select
from sqlalchemy.sql.elements import ColumnElement

from igab.db.models import Account, Category, CategoryGroup, Tag, Transaction, category_tags
from igab.repositories.txn_filters import (
    COUNTERPART_ACCOUNT_ID,
    COUNTERPART_OFF_BUDGET,
    TRANSFER_LEG,
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


def _tagged(*system_keys: str):
    # Guarded by the NOT NULL test: `NULL IN (...)` is UNKNOWN, not FALSE, and
    # a CASE arm evaluating to UNKNOWN differs from one evaluating FALSE only
    # by luck of ordering. Keep every arm two-valued.
    return and_(
        Transaction.category_id.isnot(None),
        Transaction.category_id.in_(
            select(category_tags.c.category_id)
            .join(Tag, Tag.id == category_tags.c.tag_id)
            .where(
                Tag.system_key.in_(system_keys),
                Tag.is_deleted == False,  # noqa: E712
            )
        ),
    )


#: Inflow categories (YNAB's "Ready to Assign"). A categorized inflow to an
#: ordinary category is a refund, which nets against that category's spending —
#: calling it income would double-count it and inflate a savings rate's
#: denominator.
_IN_SYSTEM_GROUP = and_(
    Transaction.category_id.isnot(None),
    Transaction.category_id.in_(
        select(Category.id)
        .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
        .where(CategoryGroup.is_system == True)  # noqa: E712
    ),
)

_CATEGORIZED = Transaction.category_id.isnot(None)
_TRACKED_COUNTERPART = COUNTERPART_OFF_BUDGET

#: (condition, class, reason) in priority order. Tags come first so a user's
#: explicit statement always beats an inferred one.
RULES: list[tuple[ColumnElement[bool], ActivityClass, ActivityReason]] = [
    (_tagged("savings", "long_term_expense"), ActivityClass.SAVINGS, ActivityReason.TAGGED_SAVINGS),
    (_tagged("debt_principal"), ActivityClass.DEBT_PRINCIPAL, ActivityReason.TAGGED_DEBT),
    # Where the money went decides the class, not whether the user bothered to
    # categorize it. An uncategorized transfer to a brokerage is still saving:
    # it leaves the budget and stays in net worth. Requiring a category here
    # meant those legs fell to the neutral bucket below and vanished from the
    # savings rate — and YNAB exports are full of uncategorized
    # tracking-account transfers.
    (
        and_(TRANSFER_LEG, _TRACKED_COUNTERPART, ~_counterpart_is_liability),
        ActivityClass.SAVINGS,
        ActivityReason.TRANSFER_TO_TRACKED_ASSET,
    ),
    (
        and_(TRANSFER_LEG, _TRACKED_COUNTERPART, _counterpart_is_liability),
        ActivityClass.DEBT_PRINCIPAL,
        ActivityReason.TRANSFER_TO_TRACKED_DEBT,
    ),
    # What remains is movement between two on-budget accounts (both legs sit
    # inside the budget, so counting either double-counts), or a leg whose
    # counterpart could not be resolved. A CATEGORIZED unresolvable leg falls
    # past this to the spending rules — it keeps the meaning its category gives
    # it rather than disappearing into a neutral bucket.
    (
        and_(TRANSFER_LEG, ~_CATEGORIZED),
        ActivityClass.TRANSFER_INTERNAL,
        ActivityReason.INTERNAL_TRANSFER,
    ),
    (
        and_(_own_on_budget == False, ~_own_is_liability),  # noqa: E712
        ActivityClass.INVESTMENT_RETURN,
        ActivityReason.TRACKED_ASSET_ACTIVITY,
    ),
    (
        and_(_own_on_budget == False, _own_is_liability),  # noqa: E712
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

#: The class of a transaction row. Use in select(), group_by() and where().
ACTIVITY_CLASS = case(
    *[(condition, literal(cls.value)) for condition, cls, _ in RULES],
    else_=literal(ActivityClass.SPENDING.value),
)

#: Which rule fired, for explaining a row to the user.
ACTIVITY_REASON = case(
    *[(condition, literal(reason.value)) for condition, _, reason in RULES],
    else_=literal(ActivityReason.DEFAULT_SPENDING.value),
)

#: Joins a query must apply before it can use the expressions above, or None
#: when they are self-contained. `None` today: every column they read is
#: reached through a correlated subquery, which needs nothing from the
#: enclosing FROM.
#:
#: The seam exists because that is the thing most likely to change. Replacing
#: the subqueries with LEFT JOINs is the standing performance idea, and the
#: hazard there is not that it breaks loudly — it is that a join matching more
#: than once per transaction multiplies every total while still looking like a
#: number. `tests/integration/invariants.py` counts rows to catch exactly that,
#: and it can only do so if it builds its query the way the reports build
#: theirs. Reading this symbol is what keeps those two in step: set it here and
#: the partition check follows the reports across, at all 48 of its call sites,
#: without any of them changing.
CLASS_JOINS: Callable[[Select], Select] | None = None

#: The classes a spending report means by "spending" — everything a household
#: would call money going out, and nothing that merely moves or grows it.
SPENDING_CLASSES = (ActivityClass.SPENDING,)
#: Money that left the budget but stayed in the household's net worth.
SAVINGS_CLASSES = (ActivityClass.SAVINGS, ActivityClass.DEBT_PRINCIPAL)


def explain(reason: str) -> str:
    """Prose for a reason code, safe for an unknown value from an older row."""
    try:
        return REASON_TEXT[ActivityReason(reason)]
    except (ValueError, KeyError):
        return "it did not match any specific rule"
