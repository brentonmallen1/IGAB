"""Golden financial invariants, written against raw SQL expressions on purpose:
they must not share code (or bugs) with the repositories under test.

Rules encoded here are the specification the fixes implement:
- Split integrity: a live split parent's amount equals the sum of its live
  children; the parent carries no category; children mirror the parent's
  date and cleared state.
- Transfer integrity: legs are mutually linked and sum to zero. A leg may
  carry a category only when it sits on an on-budget account and its partner
  account is off-budget (YNAB "spending transfer" semantics).
- Money conservation: summing posted parent rows per on-budget account (the
  account-balance query shape) must equal the sum over posted leaf rows (the
  category-activity query shape) partitioned into categorized, uncategorized
  non-transfer, and uncategorized transfer buckets.
- No cross-budget references: every id a budget's rows hold resolves inside
  that same budget. Derived from the schema, so it covers columns nobody
  remembered to check.
"""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from sqlalchemy import Table, and_, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.budget_scope import (
    POLYMORPHIC_REFERENCES,
    SOFT_REFERENCES,
    Scope,
    budget_predicate,
    budget_tables,
    classify,
)
from igab.db.models import Account, Transaction


async def assert_split_integrity(session: AsyncSession) -> None:
    parents = (
        (
            await session.execute(
                select(Transaction).where(
                    Transaction.is_split == True,  # noqa: E712
                    Transaction.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    for parent in parents:
        assert parent.category_id is None, (
            f"Split parent {parent.id} carries category {parent.category_id}; "
            "split categories belong on children only"
        )
        children = (
            (
                await session.execute(
                    select(Transaction).where(
                        Transaction.parent_transaction_id == parent.id,
                        Transaction.is_deleted == False,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        assert children, f"Split parent {parent.id} has no live children"
        child_sum = sum((c.amount for c in children), Decimal("0"))
        assert child_sum == parent.amount, (
            f"Split parent {parent.id}: amount {parent.amount} != children sum {child_sum}"
        )
        for child in children:
            assert child.date == parent.date, (
                f"Split child {child.id} date {child.date} != parent date {parent.date}"
            )
            assert child.cleared == parent.cleared, (
                f"Split child {child.id} cleared '{child.cleared}' "
                f"!= parent cleared '{parent.cleared}'"
            )


async def assert_transfer_integrity(session: AsyncSession) -> None:
    legs = (
        (
            await session.execute(
                select(Transaction).where(
                    Transaction.transfer_id.isnot(None),
                    Transaction.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    by_id = {leg.id: leg for leg in legs}
    accounts = {a.id: a for a in (await session.execute(select(Account))).scalars().all()}
    for leg in legs:
        partner = by_id.get(leg.transfer_id)
        assert partner is not None, (
            f"Transfer leg {leg.id} points at {leg.transfer_id}, which is missing or deleted"
        )
        assert partner.transfer_id == leg.id, (
            f"Transfer link not mutual: {leg.id} -> {partner.id} -> {partner.transfer_id}"
        )
        assert leg.amount == -partner.amount, (
            f"Transfer legs {leg.id}/{partner.id} do not sum to zero: "
            f"{leg.amount} vs {partner.amount}"
        )
        if leg.category_id is not None:
            own = accounts[leg.account_id]
            partner_acct = accounts[partner.account_id]
            assert own.on_budget and not partner_acct.on_budget, (
                f"Transfer leg {leg.id} has a category but is not an "
                "on-budget -> off-budget spending transfer"
            )


async def assert_money_conservation(session: AsyncSession, budget_id: uuid.UUID) -> None:
    """Cross-check the two aggregation shapes used by balances vs category sums."""
    posted_on_budget = and_(
        Transaction.budget_id == budget_id,
        Transaction.is_deleted == False,  # noqa: E712
        Transaction.cleared != "pending",
        Account.on_budget == True,  # noqa: E712
    )

    async def _sum(*extra) -> Decimal:
        result = await session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .join(Account, Transaction.account_id == Account.id)
            .where(posted_on_budget, *extra)
        )
        return Decimal(str(result.scalar_one()))

    parent_total = await _sum(Transaction.parent_transaction_id.is_(None))

    leaf = Transaction.is_split == False  # noqa: E712
    categorized = await _sum(leaf, Transaction.category_id.isnot(None))
    uncategorized_plain = await _sum(
        leaf, Transaction.category_id.is_(None), Transaction.transfer_id.is_(None)
    )
    uncategorized_transfer = await _sum(
        leaf, Transaction.category_id.is_(None), Transaction.transfer_id.isnot(None)
    )

    leaf_total = categorized + uncategorized_plain + uncategorized_transfer
    assert parent_total == leaf_total, (
        "Money conservation violated: parent-row total "
        f"{parent_total} != leaf buckets {leaf_total} "
        f"(categorized {categorized} + plain {uncategorized_plain} "
        f"+ transfer {uncategorized_transfer})"
    )


async def assert_activity_class_partition(session: AsyncSession, budget_id: uuid.UUID) -> None:
    """Every posted leaf row classifies into exactly one ActivityClass, and the
    per-class sums add back up to the ungrouped total.

    This is the property that makes the taxonomy safe to build reports on. The
    CASH_FLOW_ROW bug existed because "not cash flow" was an unnamed leftover
    bucket, so a row could fall through it and be silently counted as income.
    A partition cannot have leftovers: a rule that stops matching shows up here
    as a failure rather than as a wrong number in a chart months later.

    Written against the expression under test on purpose — the check here is
    totality and conservation, which a re-implementation could not verify.

    The row count is doing a second job. If the expression ever needs joins to
    reach the columns it reads, a join that matches more than once per
    transaction inflates `classified_count` above `total_count` and fails here
    — and this runs at 48 call sites across the suite, over YNAB imports,
    reconciliations and split edits. That only holds while this query is built
    the way the reports build theirs, which is what CLASS_JOINS is for.
    """
    from igab.domain.activity_class import ACTIVITY_CLASS, CLASS_JOINS, ActivityClass

    scope = and_(
        Transaction.budget_id == budget_id,
        Transaction.is_deleted == False,  # noqa: E712
        Transaction.cleared != "pending",
        Transaction.is_split == False,  # noqa: E712
    )

    total_row = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(Transaction.amount), 0)).where(scope)
        )
    ).one()
    total_count, total_amount = total_row[0], Decimal(str(total_row[1]))

    grouped_q = (
        select(
            ACTIVITY_CLASS.label("cls"),
            func.count(),
            func.coalesce(func.sum(Transaction.amount), 0),
        )
        .where(scope)
        .group_by(ACTIVITY_CLASS)
    )
    if CLASS_JOINS is not None:
        grouped_q = CLASS_JOINS(grouped_q)
    grouped = (await session.execute(grouped_q)).all()

    by_class = {row.cls: (row[1], Decimal(str(row[2]))) for row in grouped}

    unknown = set(by_class) - {c.value for c in ActivityClass}
    assert not unknown, f"rows classified outside the enum: {unknown}"

    classified_count = sum(count for count, _ in by_class.values())
    classified_amount = sum((amount for _, amount in by_class.values()), Decimal("0"))

    assert classified_count == total_count, (
        f"activity-class partition is not total: {classified_count} classified "
        f"of {total_count} posted leaf rows"
    )
    assert classified_amount == total_amount, (
        f"activity-class sums do not conserve: {classified_amount} != {total_amount} "
        f"(by class: { {k: str(v[1]) for k, v in by_class.items()} })"
    )


async def assert_financial_invariants(session: AsyncSession, budget_id: uuid.UUID) -> None:
    await assert_split_integrity(session)
    await assert_transfer_integrity(session)
    await assert_money_conservation(session, budget_id)
    await assert_activity_class_partition(session, budget_id)
    await assert_no_cross_budget_references(session, budget_id)


def _reference_targets(table: Table, column: Any) -> Iterator[tuple[str, tuple[Any, ...]]]:
    """(target table, extra WHERE clauses) for every way this column can
    address a row — foreign key, declared soft reference, or polymorphic."""
    for fk in column.foreign_keys:
        if fk.column.table.name != table.name:
            yield fk.column.table.name, ()
        return

    key = (table.name, column.name)
    if key in SOFT_REFERENCES:
        yield SOFT_REFERENCES[key], ()
        return
    if key in POLYMORPHIC_REFERENCES:
        type_column, targets = POLYMORPHIC_REFERENCES[key]
        for value, target_name in targets.items():
            yield target_name, (table.c[type_column] == value,)


async def assert_no_cross_budget_references(session: AsyncSession, budget_id: uuid.UUID) -> None:
    """No row in this budget points at a row in another one.

    Derived from ``igab.db.budget_scope`` rather than listed, so a column
    added next month is covered the day it lands — including the ids that
    carry no foreign key to declare them (``transactions.import_batch_id``,
    ``transactions.scheduled_transaction_id``) and the polymorphic
    ``guide_bindings.entity_id``, which no metadata walk can see.

    Written for the snapshot importer, where an unremapped id would come from,
    but it holds for every writer: the YNAB importer should pass this too.
    """
    in_graph = {Scope.ROOT, Scope.OWNED, Scope.CHILD}
    scopes = classify()
    escapes: list[str] = []

    for table in budget_tables():
        for column in table.columns:
            for target_name, extra in _reference_targets(table, column):
                if scopes.get(target_name) not in in_graph:
                    # A shared table (users) is not a budget to escape from.
                    continue
                target = table.metadata.tables[target_name]
                inside = (
                    select(literal_column("1"))
                    .select_from(target)
                    .where(target.c.id == column, budget_predicate(target, budget_id))
                    .exists()
                )
                stray = (
                    select(func.count())
                    .select_from(table)
                    .where(
                        budget_predicate(table, budget_id),
                        column.is_not(None),
                        *extra,
                        ~inside,
                    )
                )
                count = (await session.execute(stray)).scalar_one()
                if count:
                    escapes.append(f"{table.name}.{column.name} -> {target_name} ({count} rows)")

    assert not escapes, (
        f"rows in this budget point outside it: {escapes}. A copy that keeps "
        f"one of these is reading another budget's data, and nothing in the "
        f"schema would have said so."
    )
