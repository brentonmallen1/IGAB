"""Reads what `domain.tracking_start` works on: the stated values behind net
worth, the rows through which accounts arrived, and when each balance last
moved.

One reader per fact, shared by every balance chart — Net Worth, Account
Composition, the Overview card, Liabilities and Savings — so a marker on one
cannot name a different arrival from the same month on another.
"""

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import (
    Account,
    Asset,
    AssetValueSnapshot,
    Liability,
    LiabilityBalanceSnapshot,
    Transaction,
)
from igab.domain.activity_class import (
    ACTIVITY_REASON,
    OPENING_BALANCE_ROW,
    ActivityReason,
    apply_class_joins,
)
from igab.domain.tracking_start import Entry, StatedValue, place_entries
from igab.repositories.txn_filters import BALANCE_ROW, LEAF, LIVE_ACCOUNT, NOT_DELETED, POSTED

ZERO = Decimal("0")


async def stated_values(session: AsyncSession, budget_id: uuid.UUID) -> list[StatedValue]:
    """Every live asset value and every debt with no account, with its dated
    series.

    Managed debts are counted through their linked account and must not
    appear here — that would count them twice. Unmanaged ones have no
    account, and without this they would vanish from net worth.
    """
    assets = (
        await session.execute(
            select(Asset.id, Asset.name, Asset.manual_value).where(
                Asset.budget_id == budget_id,
                Asset.is_deleted == False,  # noqa: E712
            )
        )
    ).all()
    debts = (
        await session.execute(
            select(Liability.id, Liability.name, Liability.manual_balance).where(
                Liability.budget_id == budget_id,
                Liability.is_deleted == False,  # noqa: E712
                Liability.linked_account_id.is_(None),
            )
        )
    ).all()
    asset_points: dict[uuid.UUID, list[tuple[date, Decimal]]] = {a.id: [] for a in assets}
    debt_points: dict[uuid.UUID, list[tuple[date, Decimal]]] = {d.id: [] for d in debts}
    if asset_points:
        for asset_id, day, value in (
            await session.execute(
                select(
                    AssetValueSnapshot.asset_id, AssetValueSnapshot.date, AssetValueSnapshot.value
                )
                .where(AssetValueSnapshot.asset_id.in_(asset_points))
                .order_by(AssetValueSnapshot.date)
            )
        ).all():
            asset_points[asset_id].append((day, value))
    if debt_points:
        for liability_id, day, balance in (
            await session.execute(
                select(
                    LiabilityBalanceSnapshot.liability_id,
                    LiabilityBalanceSnapshot.date,
                    LiabilityBalanceSnapshot.balance,
                )
                .where(LiabilityBalanceSnapshot.liability_id.in_(debt_points))
                .order_by(LiabilityBalanceSnapshot.date)
            )
        ).all():
            debt_points[liability_id].append((day, balance))
    return [
        *(
            StatedValue(
                kind="stated_asset",
                id=str(a.id),
                name=a.name,
                current=max(ZERO, a.manual_value or ZERO),
                points=tuple(asset_points[a.id]),
            )
            for a in assets
        ),
        *(
            StatedValue(
                kind="manual_debt",
                id=str(d.id),
                name=d.name,
                current=max(ZERO, d.manual_balance or ZERO),
                points=tuple(debt_points[d.id]),
            )
            for d in debts
        ),
    ]


async def opening_entries(
    session: AsyncSession, budget_id: uuid.UUID, since: date, through: date
) -> list[Entry]:
    """Accounts arriving in the register between `since` and `through`: the
    net of their opening rows (`OPENING_BALANCE_ROW`) per account per day and
    reason — a Starting Balance is the account arriving (`account`), history
    from before its budget start the rest of its position (`pre_start`).

    Leaves, because a class is a leaf's: a pre-start split whose legs someone
    filed counts as its legs say, not as the unfiled parent. They sum to the
    parent the balance reads, so the two stay reconcilable. Every live
    account, closed ones included, as the balance sheet counts them.
    """
    rows = (
        await session.execute(
            apply_class_joins(
                select(
                    Transaction.account_id,
                    Account.name,
                    Transaction.date,
                    ACTIVITY_REASON.label("reason"),
                    func.sum(Transaction.amount).label("amount"),
                )
                .join(Account, Account.id == Transaction.account_id)
                .where(
                    Account.budget_id == budget_id,
                    LIVE_ACCOUNT,
                    NOT_DELETED,
                    POSTED,
                    LEAF,
                    OPENING_BALANCE_ROW,
                    Transaction.date >= since,
                    Transaction.date <= through,
                )
                .group_by(Transaction.account_id, Account.name, Transaction.date, ACTIVITY_REASON)
            )
        )
    ).all()
    return [
        Entry(
            kind="pre_start" if r.reason == ActivityReason.BEFORE_BUDGET_START else "account",
            id=str(r.account_id),
            name=r.name,
            day=r.date,
            amount=r.amount,
        )
        for r in rows
    ]


async def entries_by_point(
    session: AsyncSession,
    budget_id: uuid.UUID,
    cutoffs: Sequence[date],
    since: date,
    today: date,
    stated: Sequence[StatedValue],
) -> list[list[Entry]]:
    """What entered the total in each point's stretch (`place_entries`):
    accounts through their opening rows, and each stated value at its first
    point. `stated` is the caller's, read once beside the balances it
    totals."""
    if not cutoffs:
        return []
    entries = await opening_entries(session, budget_id, since, cutoffs[-1])
    entries += [e for s in stated if (e := s.entry(today)) is not None]
    return place_entries(entries, cutoffs, since)


async def last_moved(
    session: AsyncSession, account_ids: Sequence[uuid.UUID], through: date
) -> dict[uuid.UUID, date]:
    """Each account's newest balance row on or before `through`. An account
    with none is absent: it has no balance to call stale."""
    if not account_ids:
        return {}
    rows = await session.execute(
        select(Transaction.account_id, func.max(Transaction.date))
        .where(
            Transaction.account_id.in_(account_ids),
            BALANCE_ROW,
            Transaction.amount != 0,
            Transaction.date <= through,
        )
        .group_by(Transaction.account_id)
    )
    return {account_id: day for account_id, day in rows.all()}
