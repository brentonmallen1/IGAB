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

The rules are ordered and first-match-wins, so each one also carries a stable
`ActivityReason`. That is what lets the UI answer "why is this savings?" with
"transfer to an off-budget asset account" instead of asking the user to trust
an opaque reclassification.
"""

from enum import StrEnum

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from igab.db.models import Account, Category, CategoryGroup, Payee, Tag, Transaction, category_tags
from igab.repositories.txn_filters import TRANSFER_LEG


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

_LIABILITY = "liability"

_partner = aliased(Transaction)

#: The account on the other side of a transfer. The partner link is preferred;
#: an orphaned leg falls back to the account its transfer payee names, which is
#: the same signal TRANSFER_LEG uses to recognise it at all.
# `.correlate(Transaction)` is load-bearing, not decoration. These sit inside
# another scalar subquery whose FROM is `accounts`, and SQLAlchemy only
# auto-correlates against the immediately enclosing SELECT — so without it the
# planner adds `transactions` to the inner FROM and the subquery cross-joins,
# returning many rows where one is required.
_counterpart_account_id = func.coalesce(
    select(_partner.account_id)
    .where(_partner.id == Transaction.transfer_id)
    .correlate(Transaction)
    .scalar_subquery(),
    select(Payee.transfer_account_id)
    .where(Payee.id == Transaction.payee_id)
    .correlate(Transaction)
    .scalar_subquery(),
)


def _account_field(account_id, column):
    return select(column).where(Account.id == account_id).correlate(Transaction).scalar_subquery()


_counterpart_on_budget = _account_field(_counterpart_account_id, Account.on_budget)
_counterpart_is_liability = (
    _account_field(_counterpart_account_id, Account.classification) == _LIABILITY
)
_own_on_budget = _account_field(Transaction.account_id, Account.on_budget)
_own_is_liability = _account_field(Transaction.account_id, Account.classification) == _LIABILITY


def _tagged(*system_keys: str):
    return Transaction.category_id.in_(
        select(category_tags.c.category_id)
        .join(Tag, Tag.id == category_tags.c.tag_id)
        .where(
            Tag.system_key.in_(system_keys),
            Tag.is_deleted == False,  # noqa: E712
        )
    )


#: Inflow categories (YNAB's "Ready to Assign"). A categorized inflow to an
#: ordinary category is a refund, which nets against that category's spending —
#: calling it income would double-count it and inflate a savings rate's
#: denominator.
_IN_SYSTEM_GROUP = Transaction.category_id.in_(
    select(Category.id)
    .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
    .where(CategoryGroup.is_system == True)  # noqa: E712
)

_CATEGORIZED = Transaction.category_id.isnot(None)
_TRACKED_COUNTERPART = _counterpart_on_budget == False  # noqa: E712

#: (condition, class, reason) in priority order. Tags come first so a user's
#: explicit statement always beats an inferred one.
RULES: list[tuple[ColumnElement[bool], ActivityClass, ActivityReason]] = [
    (_tagged("savings", "long_term_expense"), ActivityClass.SAVINGS, ActivityReason.TAGGED_SAVINGS),
    (_tagged("debt_principal"), ActivityClass.DEBT_PRINCIPAL, ActivityReason.TAGGED_DEBT),
    (
        and_(TRANSFER_LEG, _CATEGORIZED, _TRACKED_COUNTERPART, ~_counterpart_is_liability),
        ActivityClass.SAVINGS,
        ActivityReason.TRANSFER_TO_TRACKED_ASSET,
    ),
    (
        and_(TRANSFER_LEG, _CATEGORIZED, _TRACKED_COUNTERPART, _counterpart_is_liability),
        ActivityClass.DEBT_PRINCIPAL,
        ActivityReason.TRANSFER_TO_TRACKED_DEBT,
    ),
    # Uncategorized legs are internal movement. A CATEGORIZED leg whose
    # counterpart could not be resolved deliberately falls past this to the
    # spending rules — it keeps the meaning its category gives it rather than
    # disappearing into a neutral bucket.
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
    (
        and_(Transaction.amount > 0, or_(~_CATEGORIZED, _IN_SYSTEM_GROUP)),
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
