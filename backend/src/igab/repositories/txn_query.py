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

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import (
    Account,
    Category,
    CategoryGroup,
    Payee,
    Transaction,
    TransactionAttachment,
)
from igab.domain.activity_class import ACTIVITY_CLASS, NecessityTier, apply_class_joins
from igab.repositories.txn_filters import (
    CASH_FLOW_ROW,
    LEAF,
    NEEDS_CATEGORY,
    NOT_DELETED,
    NOT_RECONCILED,
    PARENT_ROW,
    POSTED,
    UNPAIRED_TRANSFER_LEG,
    in_category_scope,
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
    activity_classes: list[str] | None = None
    necessity_tier: NecessityTier | None = None
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


def _scope_and_class(f: TransactionFilters, scope: str, necessity_where: list | None) -> list:
    """Which rows count at all: live, the right side of a split, and inside
    whatever class or tier the caller is asking about."""
    where: list[Any] = [NOT_DELETED, LEAF if scope == "leaf" else PARENT_ROW]
    if f.posted_only:
        where.append(POSTED)
    if f.cash_flow_only:
        where.append(CASH_FLOW_ROW)
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
    if f.payee_ids:
        where.append(Transaction.payee_id.in_(f.payee_ids))
    if f.account_ids:
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
        class_joins=bool(f.activity_classes) or f.necessity_tier is not None,
        payee_join=bool(f.search),
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
        func.coalesce(Category.name, "Uncategorized"),
        needs=("category",),
        description="Envelope name.",
    ),
    "category_group": Dimension(
        func.coalesce(CategoryGroup.name, "Uncategorized"),
        needs=("category", "category_group"),
        description="The group an envelope sits in.",
    ),
    "payee": Dimension(
        func.coalesce(Payee.name, "(no payee)"),
        needs=("payee",),
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

#: Every legal `aggregate`, over the row amount.
AGGREGATES: dict[str, Any] = {
    "sum": lambda: func.coalesce(func.sum(Transaction.amount), 0),
    "count": lambda: func.count(),
    "avg": lambda: func.coalesce(func.avg(Transaction.amount), 0),
    "min": lambda: func.coalesce(func.min(Transaction.amount), 0),
    "max": lambda: func.coalesce(func.max(Transaction.amount), 0),
}

#: No query may return more groups than this, whatever it asks for. A
#: thousand payees is not an answer anyone reads, and it is a lot of tokens
#: to send an assistant that will summarize the top few anyway.
MAX_GROUPS = 200


def _apply_dimension_joins(q: Select, needs: tuple[str, ...]) -> Select:
    if "category" in needs:
        q = q.outerjoin(Category, Transaction.category_id == Category.id)
    if "category_group" in needs:
        q = q.outerjoin(CategoryGroup, Category.category_group_id == CategoryGroup.id)
    if "payee" in needs:
        q = q.outerjoin(Payee, Transaction.payee_id == Payee.id)
    if "account" in needs:
        q = q.join(Account, Transaction.account_id == Account.id)
    return q


async def grouped_totals(
    session: AsyncSession,
    budget_id: uuid.UUID,
    *,
    group_by: str,
    aggregate: str = "sum",
    filters: TransactionFilters | None = None,
    necessity_where: list | None = None,
    order: str = "value",
    limit: int = 50,
) -> tuple[list[dict], int]:
    """Roll the matching rows up by one dimension.

    Returns the groups and how many there were in total — the caller needs
    the second number to say "the top 20 of 340" rather than imply 20 was
    all of them.

    The aggregate runs as a real GROUP BY, not over a fetched page: a sum of
    the first 200 rows is not the sum, and an assistant handed one would
    state it as though it were.
    """
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

    f = filters or TransactionFilters()
    # Leaf scope: split legs carry the categories, so a grouped total on
    # parent rows would miss every split — the same bug `spending_insights`
    # shipped with.
    parts = build_where(budget_id, f, scope="leaf", necessity_where=necessity_where)

    label = dimension.expression.label("group")
    value = make_aggregate().label("value")
    q: Select = select(label, value, func.count().label("rows")).select_from(Transaction)
    if parts.class_joins:
        q = apply_class_joins(q)
    needs = dimension.needs
    if parts.payee_join and "payee" not in needs:
        needs = needs + ("payee",)
    q = _apply_dimension_joins(q, needs)
    q = q.where(*parts.where).group_by(label)

    ordering = {
        "value": value.desc(),
        "group": label.asc(),
        "rows": func.count().desc(),
    }.get(order, value.desc())

    counted = await session.execute(select(func.count()).select_from(q.order_by(None).subquery()))
    total_groups = int(counted.scalar() or 0)

    rows = (await session.execute(q.order_by(ordering).limit(min(limit, MAX_GROUPS)))).all()
    groups = [
        {
            "group": (row.group or "").strip() if isinstance(row.group, str) else row.group,
            "value": Decimal(row.value) if aggregate != "count" else int(row.value),
            "rows": int(row.rows),
        }
        for row in rows
    ]
    return groups, total_groups
