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
"""

import uuid
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    accounts = {
        a.id: a
        for a in (await session.execute(select(Account))).scalars().all()
    }
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


async def assert_financial_invariants(session: AsyncSession, budget_id: uuid.UUID) -> None:
    await assert_split_integrity(session)
    await assert_transfer_integrity(session)
    await assert_money_conservation(session, budget_id)
