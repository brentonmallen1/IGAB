"""Differential testing for the activity-class expression.

Enumerating cases finds the cases you thought of. `test_activity_class_matrix`
pins 24 of them and is worth every line, but it cannot tell you about the shape
neither the author nor the reviewer imagined — and this expression is built
from correlated subqueries whose NULL behaviour is subtle enough that
`activity_class.py` carries four separate comments about it.

So: run two implementations over the same realistic budget and require that
they agree about **every** row. Class *and* reason, because two rules can
arrive at the same class with the wrong one firing, and a class-only
comparison would call that identical.

The other thing this catches, and the reason it exists at all: a join-based
implementation that fans out returns a row per *join match* rather than per
transaction. Totals silently multiply, which reads as a plausible number
rather than as an error. `_classify` refuses to return before checking that.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from igab.db.models import Account, Category, Transaction
from igab.domain.activity_class import CLASS_JOINS
from igab.repositories.txn_filters import LEAF, NOT_DELETED, POSTED

#: Sentinel: `joins=None` means "whatever the shipped expression needs", which
#: is not the same statement as "no joins" — a candidate implementation must be
#: able to say the latter explicitly.
_DEFAULT = object()


@dataclass(frozen=True)
class ClassImpl:
    """One way of computing a row's activity class.

    `joins` is what makes this able to describe a join-based implementation:
    the expression alone is not the whole story once the columns it reads have
    to be brought into the query. Anything that applies the expression must
    apply the joins, which is exactly the property a differential test needs
    to be checking.
    """

    name: str
    cls: ColumnElement
    reason: ColumnElement
    joins: Callable[[Select], Select] | None | object = _DEFAULT

    def apply(self, stmt: Select) -> Select:
        joins = CLASS_JOINS if self.joins is _DEFAULT else self.joins
        return stmt if joins is None else joins(stmt)  # type: ignore[operator]


def scope(budget_id: uuid.UUID):
    """The rows the taxonomy claims to partition: posted leaf rows."""
    return (Transaction.budget_id == budget_id, NOT_DELETED, POSTED, LEAF)


async def _classify(
    session: AsyncSession, budget_id: uuid.UUID, impl: ClassImpl
) -> dict[uuid.UUID, tuple[str, str]]:
    stmt = select(
        Transaction.id,
        impl.cls.label("cls"),
        impl.reason.label("reason"),
    ).where(*scope(budget_id))
    stmt = impl.apply(stmt)

    rows = (await session.execute(stmt)).all()
    distinct = len({r.id for r in rows})
    assert len(rows) == distinct, (
        f"{impl.name} returned {len(rows)} rows for {distinct} transactions — "
        "the joins fan out. Every total computed through this expression would "
        "be multiplied, which looks like a number rather than like an error."
    )
    return {r.id: (r.cls, r.reason) for r in rows}


async def _describe(session: AsyncSession, txn_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Enough of a row's shape to diagnose why two implementations disagree."""
    rows = (
        await session.execute(
            select(
                Transaction.id,
                Transaction.date,
                Transaction.amount,
                Transaction.transfer_id,
                Category.name.label("category"),
                Account.name.label("account"),
                Account.on_budget,
                Account.classification,
            )
            .outerjoin(Category, Category.id == Transaction.category_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(Transaction.id.in_(txn_ids))
        )
    ).all()
    return {
        r.id: (
            f"{r.date} {r.amount:>10} on {r.account!r} "
            f"({'on' if r.on_budget else 'off'}-budget {r.classification}) "
            f"category={r.category!r} transfer={'yes' if r.transfer_id else 'no'}"
        )
        for r in rows
    }


async def assert_class_agreement(
    session: AsyncSession,
    budget_id: uuid.UUID,
    reference: ClassImpl,
    candidate: ClassImpl,
    *,
    max_report: int = 8,
) -> int:
    """Both implementations classify every row identically. Returns the count.

    A rewrite that preserves behaviour passes this over a full-tier budget —
    thousands of rows, real transfers, splits, a mortgage, a tracked brokerage.
    One that does not fails naming the rows and what each side thought.
    """
    ref = await _classify(session, budget_id, reference)
    cand = await _classify(session, budget_id, candidate)

    assert ref.keys() == cand.keys(), (
        f"{reference.name} classified {len(ref)} rows, {candidate.name} classified "
        f"{len(cand)} — they disagree about which rows are in scope"
    )
    assert ref, "nothing to compare: the budget has no posted leaf rows"

    disagree = [txn_id for txn_id, value in ref.items() if cand[txn_id] != value]
    if not disagree:
        return len(ref)

    shapes = await _describe(session, disagree[:max_report])
    lines = [
        f"  {shapes.get(txn_id, txn_id)}\n"
        f"      {reference.name}: {ref[txn_id][0]} ({ref[txn_id][1]})\n"
        f"      {candidate.name}: {cand[txn_id][0]} ({cand[txn_id][1]})"
        for txn_id in disagree[:max_report]
    ]
    more = "" if len(disagree) <= max_report else f"\n  …and {len(disagree) - max_report} more"
    raise AssertionError(
        f"{reference.name} and {candidate.name} disagree about "
        f"{len(disagree)} of {len(ref)} rows:\n" + "\n".join(lines) + more
    )
