"""One WHERE clause over transactions, and the grouped rollup that shares it.

Two callers need the same filtering: the register's listing
(`TransactionRepository.list_for_budget`) and the grouped rollup an assistant
asks for through `query_transactions`. That clause is about a hundred lines of
accumulated bug fixes — split legs versus parent rows, the tier scope a chart
counted, transfers that have a payee but no partner — and a second copy would
drift from the first the week someone fixed one of them. So it is built here,
once, and both callers pass the same `TransactionFilters` into it.

It is a pure function of its arguments: no session, no await. That is what
makes every branch testable without a database, which is the only way a clause
this long stays honest.

**The vocabulary is closed, which is what makes this safe to expose.**
`query_transactions` hands a model's arguments straight into `GROUPABLE` and
`AGGREGATES` below — as *keys*, never as SQL. A name that is not in those
dicts raises `UnknownDimension`; nothing a model writes is ever interpolated
into a statement, only used to look up an expression this module already
built. The budget is a parameter of the call, not of the query, so no
argument can widen the scope to another budget. And there is exactly one
statement shape here, a SELECT — there is no write to reach.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, case, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from igab.db.models import (
    Account,
    Category,
    CategoryGroup,
    Payee,
    Transaction,
    TransactionAttachment,
)
from igab.domain.activity_class import (
    ACTIVITY_CLASS,
    DISCRETIONARY_ROW,
    NecessityTier,
    apply_class_joins,
)
from igab.domain.spending import (
    NO_CATEGORY_LABEL,
    OFF_BUDGET_LABEL,
    TRANSFER_LABEL,
    UNCATEGORIZED,
)
from igab.repositories.plan_rows import PLAN_SPENT_ROW
from igab.repositories.txn_filters import (
    CASH_FLOW_ROW,
    LEAF,
    NEEDS_CATEGORY,
    NOT_DELETED,
    NOT_RECONCILED,
    ON_BUDGET_ACCOUNT,
    PARENT_ROW,
    PAYEE_OF_RECORD,
    POSTED,
    TRANSFER_LEG,
    UNPAIRED_TRANSFER_LEG,
    in_category_scope,
    join_split_parent,
    search_matches,
)


@dataclass(frozen=True)
class TransactionFilters:
    """Every way the register and the tools can narrow a set of rows.

    One dataclass rather than thirty keyword arguments repeated per caller:
    the listing already had them, and a grouped query that supported a
    different subset would be a second answer to "which rows count".
    """

    start_date: date | None = None
    end_date: date | None = None
    search: str | None = None
    category_ids: list[uuid.UUID] | None = None
    payee_ids: list[uuid.UUID] | None = None
    account_ids: list[uuid.UUID] | None = None
    posted_only: bool = False
    cash_flow_only: bool = False
    #: Only rows on on-budget accounts (`ON_BUDGET_ACCOUNT`) — the budget's
    #: own money. Off by default so the register, which lists a tracking
    #: account's rows when you open it, is untouched; the assistant's tools
    #: turn it on unless the question names an account, as `account_scope`
    #: lets a report's explicit selection override the same default.
    on_budget_only: bool = False
    activity_classes: list[str] | None = None
    necessity_tier: NecessityTier | None = None
    #: Only discretionary spending (`activity_class.DISCRETIONARY_ROW`), the
    #: rows the Discretionary report totals. A flag rather than a fourth
    #: tier: see there for why it is not a `NecessityTier`.
    discretionary: bool = False
    #: Only the rows a plan report counts as spent (`plan_rows.PLAN_SPENT_ROW`)
    #: — both ways, so a figure net of refunds opens a list that totals it.
    plan_spent: bool = False
    direction: str | None = None
    day_of_week: int | None = None
    cleared: str | None = None
    exclude_cleared: str | None = None
    unreconciled: bool = False
    uncategorized: bool = False
    no_category: bool = False
    unapproved: bool = False
    is_or_mode: bool = False
    amount_min: float | None = None
    amount_max: float | None = None
    has_attachment: bool | None = None
    is_transfer: bool | None = None
    unpaired_transfers: bool = False


@dataclass(frozen=True)
class WhereParts:
    """The clause, and which joins it made necessary."""

    where: list[Any] = field(default_factory=list)
    #: Four LEFT JOINs. Only when a class or tier filter is in play — the
    #: ordinary register listing has no reason to pay for them.
    class_joins: bool = False
    #: `search` matches on payee name, which needs the payee table.
    payee_join: bool = False
    #: A payee filter reads `PAYEE_OF_RECORD`, which needs the row's split
    #: parent: apply `join_split_parent`.
    split_parent_join: bool = False


def _scope_and_class(f: TransactionFilters, scope: str, necessity_where: list | None) -> list:
    """Which rows count at all: live, the right side of a split, and inside
    whatever class or tier the caller is asking about."""
    where: list[Any] = [NOT_DELETED, LEAF if scope == "leaf" else PARENT_ROW]
    if f.posted_only:
        where.append(POSTED)
    if f.cash_flow_only:
        where.append(CASH_FLOW_ROW)
    if f.on_budget_only:
        where.append(ON_BUDGET_ACCOUNT)
    if f.activity_classes:
        # So a drill-down lists exactly what the chart that opened it
        # counted. Without this an $800 "Expenses" bar opened a panel
        # totalling $1,800, because the bar means SPENDING and the list
        # meant every negative row.
        where.append(ACTIVITY_CLASS.in_(list(f.activity_classes)))
    if necessity_where:
        # A tier's membership is per ROW once debt principal joins it by
        # class, so a bar's category ids alone list rows the tier never
        # counted: an "Auto" bar holding a $340 loan payment opened $420
        # with the fuel beside it. The tier's own scope — the report's
        # rule, fallback included — is what the panel lists.
        where.extend(necessity_where)
    if f.discretionary:
        # The report's own predicate, not categories plus a class: a line's
        # ids alone also list rows filed there that are not discretionary
        # spending — a move to savings, a purchase on an off-budget account.
        # No fallback to resolve, so unlike a tier it needs no session.
        where.append(DISCRETIONARY_ROW)
    if f.plan_spent:
        # The plan ledger's own rows, not a category's outflows: those left
        # out its refunds and a savings envelope's transfers out, and listed
        # an untagged envelope's brokerage transfer it never counted.
        where.append(PLAN_SPENT_ROW)
    return where


def _dates_and_amounts(f: TransactionFilters) -> list:
    """When, which way the money went, and how much of it."""
    where: list[Any] = []
    if f.direction == "outflow":
        where.append(Transaction.amount < 0)
    elif f.direction == "inflow":
        where.append(Transaction.amount > 0)
    if f.start_date:
        where.append(Transaction.date >= f.start_date)
    if f.end_date:
        where.append(Transaction.date <= f.end_date)
    if f.amount_min is not None:
        where.append(func.abs(Transaction.amount) >= f.amount_min)
    if f.amount_max is not None:
        where.append(func.abs(Transaction.amount) <= f.amount_max)
    if f.day_of_week is not None:
        # isodow is Monday=1..Sunday=7; the API uses Monday=0..Sunday=6
        where.append(func.extract("isodow", Transaction.date) == f.day_of_week + 1)
    return where


def _relations(f: TransactionFilters, scope: str) -> list:
    """What the row points at: envelope, payee, account, the other leg."""
    where: list[Any] = []
    if f.category_ids is not None:
        # Parent rows scope by their legs too. The Timeline shows a split
        # scoped to one of its legs' categories (`in_category_scope`), and
        # clicking its card opened this listing with a plain IN that
        # excludes every split parent — "No transactions match" for the
        # row just clicked.
        where.append(
            in_category_scope(f.category_ids)
            if scope == "parent"
            else Transaction.category_id.in_(f.category_ids)
        )
    if f.no_category:
        where.append(Transaction.category_id.is_(None))
    # The payee of record: a split leg's own payee, else its parent's. The
    # legs of a split usually carry none — the parent names the shop — so on
    # leaf scope the raw column dropped every leg, and the Pareto payee bar
    # (which ranks by payee of record) opened a list short by every split
    # purchase. A parent row has no split parent, so on parent scope, the
    # register's, this is the row's own payee exactly as before.
    #
    # `is not None`: an empty list is a filter that matches nothing. The
    # assistant's tools pass [] for a payee name that resolved to nobody, and
    # a truthiness test turned that into "every payee".
    if f.payee_ids is not None:
        where.append(PAYEE_OF_RECORD.in_(f.payee_ids))
    # `is not None`, as for payees: the assistant's tools pass [] for an
    # account name that resolved to nothing, and a truthiness test read that
    # as "every account" and answered with the whole budget.
    if f.account_ids is not None:
        where.append(Transaction.account_id.in_(f.account_ids))
    if f.is_transfer is not None:
        where.append(
            Transaction.transfer_id.is_not(None)
            if f.is_transfer
            else Transaction.transfer_id.is_(None)
        )
    # Deliberately its own filter rather than a mode of `is_transfer`: that
    # one tests transfer_id alone, so it cannot express "has a transfer
    # payee but no partner" at all.
    if f.unpaired_transfers:
        where.append(UNPAIRED_TRANSFER_LEG)
    return where


def _state(f: TransactionFilters) -> list:
    """What still has to happen to the row, and what it says."""
    where: list[Any] = []
    if f.cleared:
        where.append(Transaction.cleared == f.cleared)
    if f.exclude_cleared:
        where.append(Transaction.cleared != f.exclude_cleared)
    if f.unreconciled:
        where.append(NOT_RECONCILED)
    # The same rule the needs-attention badge counts. They disagreed: this
    # excluded neither transfers nor off-budget rows, so pressing the badge
    # opened a list longer than the badge promised.
    if f.uncategorized and f.unapproved and f.is_or_mode:
        where.append(or_(NEEDS_CATEGORY, Transaction.approved == False))  # noqa: E712
    else:
        if f.uncategorized:
            where.append(NEEDS_CATEGORY)
        if f.unapproved:
            where.append(Transaction.approved == False)  # noqa: E712
    if f.has_attachment is not None:
        attachment_exists = (
            select(TransactionAttachment.id)
            .where(TransactionAttachment.transaction_id == Transaction.id)
            .exists()
        )
        where.append(attachment_exists if f.has_attachment else ~attachment_exists)
    if f.search:
        where.append(search_matches(f.search))
    return where


def build_where(
    budget_id: uuid.UUID,
    f: TransactionFilters,
    *,
    scope: str = "parent",
    necessity_where: list | None = None,
) -> WhereParts:
    """The clause both callers use.

    `scope="leaf"` selects category-carrying rows (split children included,
    parents excluded); `scope="parent"` selects account-balance rows.

    `necessity_where` is resolved by the caller rather than here:
    `TransactionRepository._necessity_scope` needs a session to read which
    categories carry the tier's tags, and five other methods already call it.
    Passing its answer in keeps this function pure.

    Split into four by concern because one function carrying every branch
    tripped the complexity gate, and the per-file exemption list says in
    writing to prefer shrinking it to adding to it.
    """
    return WhereParts(
        where=[
            Transaction.budget_id == budget_id,
            *_scope_and_class(f, scope, necessity_where),
            *_dates_and_amounts(f),
            *_relations(f, scope),
            *_state(f),
        ],
        class_joins=bool(f.activity_classes)
        or f.necessity_tier is not None
        or f.discretionary
        or f.plan_spent,
        payee_join=bool(f.search),
        split_parent_join=f.payee_ids is not None,
    )


# ── the closed vocabulary ────────────────────────────────────────────────


class UnknownDimension(ValueError):
    """A group-by or aggregate that is not in the vocabulary.

    Raised rather than ignored: silently grouping by something else would
    answer a question nobody asked, and an assistant would report the answer
    as though it were the one requested.
    """


@dataclass(frozen=True)
class Dimension:
    """One thing rows can be grouped by."""

    #: What to select and group on.
    expression: Any
    #: Joins this dimension needs beyond the base table.
    needs: tuple[str, ...] = ()
    description: str = ""


#: The payee a grouped row is filed under (`PAYEE_OF_RECORD`). Its own alias:
#: `search` joins `Payee` on the row's own payee, as the listing does, and one
#: join serving both would change what a search matches under a payee rollup.
PAYEE_OF_ROW = aliased(Payee, name="payee_of_record")


def _named_or_why(name: Any) -> Any:
    """A category or group name, or — for a row with none — the reason it has
    none.

    `UNCATEGORIZED` only for a row that needs a category, by the app's one
    rule (`NEEDS_CATEGORY`), so the rollup's Uncategorized line is the rows
    the register's Uncategorized filter lists. Coalescing every NULL to it
    filed a tracking account's market adjustments and a mortgage payment's
    loan leg there, and ranked "Uncategorized" first at three times the
    month's real spending.

    Off-budget before Transfer: a row on a tracking account is outside the
    budget whatever else it is, and the loan leg of a mortgage payment is the
    tracked side of a transfer the budget sees only from checking.

    These are correlated subqueries, which Postgres will not match between a
    SELECT list and a GROUP BY — so `grouped_totals` computes the label per
    row in an inner select and groups the outer one by its column.
    """
    return case(
        (name.is_not(None), name),
        (NEEDS_CATEGORY, UNCATEGORIZED),
        (not_(ON_BUDGET_ACCOUNT), OFF_BUDGET_LABEL),
        (TRANSFER_LEG, TRANSFER_LABEL),
        else_=NO_CATEGORY_LABEL,
    )


_NO_CATEGORY_DESCRIPTION = (
    f"A row with none reads {UNCATEGORIZED} only when it needs one; otherwise "
    f"{TRANSFER_LABEL}, {OFF_BUDGET_LABEL} or {NO_CATEGORY_LABEL}."
)


#: Every legal `group_by`. A model picks a KEY here; the expression is one
#: this module wrote. Nothing from the caller reaches the statement as SQL.
GROUPABLE: dict[str, Dimension] = {
    "month": Dimension(
        func.to_char(func.date_trunc("month", Transaction.date), "YYYY-MM"),
        description="Calendar month, YYYY-MM.",
    ),
    "day_of_week": Dimension(
        func.to_char(Transaction.date, "Day"),
        description="Monday … Sunday.",
    ),
    "category": Dimension(
        _named_or_why(Category.name),
        needs=("category",),
        description=f"Envelope name. {_NO_CATEGORY_DESCRIPTION}",
    ),
    "category_group": Dimension(
        _named_or_why(CategoryGroup.name),
        needs=("category", "category_group"),
        description=f"The group an envelope sits in. {_NO_CATEGORY_DESCRIPTION}",
    ),
    # The payee of record, as the payee filter and the Pareto and Payee
    # Analysis bars read it. The rollup is leaf-scoped and a split's legs
    # usually carry no payee — the parent names the shop — so grouping by the
    # raw column filed every split purchase under "(no payee)", beside the
    # same shop's unsplit rows.
    "payee": Dimension(
        func.coalesce(PAYEE_OF_ROW.name, "(no payee)"),
        needs=("payee_of_record",),
        description="Who was paid.",
    ),
    "account": Dimension(
        Account.name,
        needs=("account",),
        description="Which account the row is on.",
    ),
    "cleared": Dimension(
        Transaction.cleared,
        description="pending, uncleared, cleared or reconciled.",
    ),
}

#: Every legal `aggregate`, over a column of row amounts.
AGGREGATES: dict[str, Any] = {
    "sum": lambda amount: func.coalesce(func.sum(amount), 0),
    "count": lambda amount: func.count(),
    "avg": lambda amount: func.coalesce(func.avg(amount), 0),
    "min": lambda amount: func.coalesce(func.min(amount), 0),
    "max": lambda amount: func.coalesce(func.max(amount), 0),
}

#: The aggregates whose group values add up to something: a sum of sums is
#: the total, a sum of counts is the row count. A sum of averages, minimums
#: or maximums means nothing, so those report only how many groups were cut.
ADDITIVE_AGGREGATES = frozenset({"sum", "count"})

#: How many groups a rollup returns when the caller does not say. One home:
#: the tool handler, the repository and the registry's text all read it.
#: It was written as 25 in three of those places and 50 in this one.
DEFAULT_GROUPS = 50

#: No query may return more groups than this, whatever it asks for. A
#: thousand payees is not an answer anyone reads, and it is a lot of tokens
#: to send an assistant. It was 100 in the tool handler and 200 here, so the
#: registry promised a ceiling this module did not enforce.
MAX_GROUPS = 100


def group_limit(value: Any) -> int:
    """How many groups to return: `DEFAULT_GROUPS` when unsaid or unreadable,
    clamped to 1..`MAX_GROUPS`.

    The one clamp. The handler clamped to at least one; this module did not,
    so a limit of 0 returned no groups and a negative one was a Postgres
    error rather than an answer.
    """
    if value is None or isinstance(value, bool):
        return DEFAULT_GROUPS
    try:
        wanted = int(value)
    except (TypeError, ValueError):
        return DEFAULT_GROUPS
    return max(1, min(MAX_GROUPS, wanted))


@dataclass(frozen=True)
class GroupedTotals:
    """A rollup's groups, and what the cut left out.

    Every figure but `groups` is computed over ALL matching groups, not the
    page — the caller needs them to say "50 of 63; the other 13 total
    -1,234.56" rather than imply the page was everything.
    """

    groups: list[dict]
    #: How many groups matched before the limit.
    total_groups: int
    #: The value across every group: the whole sum, or the whole row count.
    #: None for an aggregate whose groups do not add up (`ADDITIVE_AGGREGATES`).
    total: Decimal | int | None = None
    #: The combined value of the groups below the cut, on the same terms.
    omitted_value: Decimal | int | None = None

    @property
    def omitted_groups(self) -> int:
        return self.total_groups - len(self.groups)


def _apply_dimension_joins(q: Select, needs: tuple[str, ...]) -> Select:
    if "payee_of_record" in needs:
        q = q.outerjoin(PAYEE_OF_ROW, PAYEE_OF_RECORD == PAYEE_OF_ROW.id)
    if "category" in needs:
        q = q.outerjoin(Category, Transaction.category_id == Category.id)
    if "category_group" in needs:
        q = q.outerjoin(CategoryGroup, Category.category_group_id == CategoryGroup.id)
    if "payee" in needs:
        q = q.outerjoin(Payee, Transaction.payee_id == Payee.id)
    if "account" in needs:
        q = q.join(Account, Transaction.account_id == Account.id)
    return q


def _vocabulary(group_by: str, aggregate: str) -> tuple[Dimension, Any]:
    dimension = GROUPABLE.get(group_by)
    if dimension is None:
        raise UnknownDimension(
            f"{group_by!r} is not something rows can be grouped by. "
            f"Choose one of: {', '.join(sorted(GROUPABLE))}."
        )
    make_aggregate = AGGREGATES.get(aggregate)
    if make_aggregate is None:
        raise UnknownDimension(
            f"{aggregate!r} is not an aggregate. Choose one of: {', '.join(sorted(AGGREGATES))}."
        )
    return dimension, make_aggregate


def _labelled_rows(
    budget_id: uuid.UUID,
    dimension: Dimension,
    f: TransactionFilters,
    necessity_where: list | None,
) -> Any:
    """One row per matching transaction: its group label and its amount.

    Leaf scope: split legs carry the categories, so a grouped total on parent
    rows would miss every split — the same bug `spending_insights` shipped
    with.
    """
    parts = build_where(budget_id, f, scope="leaf", necessity_where=necessity_where)
    q: Select = select(
        dimension.expression.label("label"), Transaction.amount.label("amount")
    ).select_from(Transaction)
    if parts.class_joins:
        q = apply_class_joins(q)
    needs = dimension.needs
    if parts.split_parent_join or "payee_of_record" in needs:
        q = join_split_parent(q)
    if parts.payee_join and "payee" not in needs:
        needs = needs + ("payee",)
    q = _apply_dimension_joins(q, needs)
    return q.where(*parts.where).subquery("labelled")


async def grouped_totals(
    session: AsyncSession,
    budget_id: uuid.UUID,
    *,
    group_by: str,
    aggregate: str = "sum",
    filters: TransactionFilters | None = None,
    necessity_where: list | None = None,
    order: str = "value",
    limit: int | None = None,
) -> GroupedTotals:
    """Roll the matching rows up by one dimension.

    The aggregate runs as a real GROUP BY, not over a fetched page: a sum of
    the first 200 rows is not the sum, and an assistant handed one would
    state it as though it were.

    `order="value"` ranks by SIZE — the absolute value, largest first. Ranking
    by the signed value put income and positive adjustments first and the
    biggest outflows (stored negative) last, so a limit cut the very spends a
    "where did my money go" question was asking about. Every order breaks
    ties by the group's label: an unordered result is a CI flake here.
    """
    dimension, make_aggregate = _vocabulary(group_by, aggregate)
    labelled = _labelled_rows(
        budget_id, dimension, filters or TransactionFilters(), necessity_where
    )
    grouped = (
        select(
            labelled.c.label.label("group"),
            make_aggregate(labelled.c.amount).label("value"),
            func.count().label("rows"),
        )
        .group_by(labelled.c.label)
        .subquery("grouped")
    )

    summary = (
        await session.execute(select(func.count(), func.sum(grouped.c.value)).select_from(grouped))
    ).one()
    total_groups = int(summary[0] or 0)

    tiebreak = grouped.c.group.asc()
    ordering = {
        "group": (tiebreak,),
        "rows": (grouped.c.rows.desc(), tiebreak),
    }.get(order, (func.abs(grouped.c.value).desc(), tiebreak))
    rows = (
        await session.execute(
            select(grouped.c.group, grouped.c.value, grouped.c.rows)
            .order_by(*ordering)
            .limit(group_limit(limit))
        )
    ).all()

    def as_value(raw: Any) -> Decimal | int:
        return int(raw or 0) if aggregate == "count" else Decimal(raw or 0)

    values = [as_value(row.value) for row in rows]
    groups = [
        {
            "group": (row.group or "").strip() if isinstance(row.group, str) else row.group,
            "value": value,
            "rows": int(row.rows),
        }
        for row, value in zip(rows, values, strict=True)
    ]
    if aggregate not in ADDITIVE_AGGREGATES:
        return GroupedTotals(groups=groups, total_groups=total_groups)
    total = as_value(summary[1])
    shown = sum(values, as_value(0))
    return GroupedTotals(
        groups=groups,
        total_groups=total_groups,
        total=total,
        omitted_value=total - shown,
    )
