"""Copy a budget, whole or as a fresh start.

Both modes are the snapshot round trip — export, then import as a new budget
— because that path already knows how to remap every id, drop the bank link
(`REDACT_ON_NEW_BUDGET`), and refuse a file this version cannot read. A
second copier would be a second answer to "what is a budget made of", and
this repo's history says the two would drift.

**Structure only** is that copy with its ledger emptied: the arrangement
(accounts, groups, categories, targets, tags, payees, filters, views, plans,
the Guide's answers) stays, and what *happened* goes. Every account keeps its
position through one Starting Balance row dated `as_of`, the same device a
first bank sync uses — so a fresh start opens on the balances you actually
have rather than on zero. Assets and liabilities keep their newest recorded
position and lose the history behind it, for the same reason.
"""

import tempfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from igab.db.budget_scope import budget_predicate, delete_order
from igab.db.models import (
    Account,
    AssetValueSnapshot,
    Base,
    LiabilityBalanceSnapshot,
    Transaction,
)
from igab.domain.payee_names import STARTING_BALANCE_PAYEE
from igab.repositories.txn_filters import BALANCE_ROW
from igab.services import budget_snapshot
from igab.services.transaction_service import TransactionCreate, TransactionService

#: What happened, as opposed to how the budget is arranged. Emptied by a
#: structure-only clone, children first. Named rather than derived: every
#: table here is a deliberate answer to "is this the plan or the past", and a
#: rule that guessed from the schema would sweep up a category plan.
LEDGER_TABLES: tuple[str, ...] = (
    "transaction_matches",
    "reconciliation_snapshots",
    "transactions",
    "budget_moves",
    "budget_assignments",
    "scheduled_transactions",
    "import_anchors",
    "import_batches",
)


@dataclass
class CloneReport:
    budget_id: UUID
    budget_name: str
    structure_only: bool
    #: Accounts given a Starting Balance row (those whose position was not
    #: zero on `as_of`).
    opening_balances: int
    row_counts: dict[str, int]


async def clone_budget(
    session: AsyncSession,
    budget_id: UUID,
    *,
    user_id: UUID,
    name: str | None = None,
    structure_only: bool = False,
    as_of: date,
    app_version: str,
    txn_service: TransactionService,
) -> CloneReport:
    """Copy `budget_id` into a new budget owned by `user_id`.

    Runs inside the caller's transaction: a failure anywhere leaves the
    database exactly as it was, and no half-built budget behind.
    """
    with tempfile.NamedTemporaryFile(suffix=budget_snapshot.SNAPSHOT_SUFFIX, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        await budget_snapshot.export_budget_snapshot(
            session,
            budget_id,
            cast(BinaryIO, tmp),
            app_version=app_version,
            alembic_revision=await budget_snapshot.current_revision(session),
        )
    try:
        report = await budget_snapshot.import_snapshot_as_new_budget(
            session, tmp_path, user_id=user_id, name=name
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    opened = 0
    if structure_only:
        opened = await _empty_the_ledger(
            session, report.budget_id, as_of=as_of, txn_service=txn_service
        )

    return CloneReport(
        budget_id=report.budget_id,
        budget_name=report.budget_name,
        structure_only=structure_only,
        opening_balances=opened,
        row_counts=report.row_counts,
    )


async def _empty_the_ledger(
    session: AsyncSession,
    budget_id: UUID,
    *,
    as_of: date,
    txn_service: TransactionService,
) -> int:
    """Drop the copy's history, keeping every position it established.

    Balances are read BEFORE the delete, from the copy's own rows and with
    the same predicate the account header uses (`BALANCE_ROW`), so the
    opening rows reproduce the figures the source shows on `as_of` rather
    than a second guess at them.
    """
    balances = await _balances_as_of(session, budget_id, as_of)

    # `budget_predicate`, not `budget_id ==`: a reconciliation or a match is
    # scoped through its account or its transaction and carries no budget_id
    # of its own. `delete_order` puts children first, so the FKs hold.
    ledger = {name for name in LEDGER_TABLES}
    for table in delete_order():
        if table.name in ledger:
            await session.execute(delete(table).where(budget_predicate(table, budget_id)))
    await _trim_position_history(session, budget_id, as_of)
    await session.flush()

    accounts = (
        (
            await session.execute(
                select(Account).where(
                    Account.budget_id == budget_id,
                    Account.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    opened = 0
    for account in accounts:
        amount = balances.get(account.id, Decimal("0"))
        if amount == 0:
            continue
        # Through the service, so the row is change-logged like any other and
        # the copy's first ⌘Z is not a surprise. Uncategorized and reconciled,
        # the same shape a first bank sync writes: on a cash account the money
        # lands in Ready to Assign, on a card it reads as pre-history debt.
        await txn_service.create(
            budget_id,
            TransactionCreate(
                account_id=account.id,
                date=as_of,
                amount=amount,
                payee_name=STARTING_BALANCE_PAYEE,
                category_id=None,
                memo="Starting position carried over from the budget this was copied from",
                cleared="reconciled",
                approved=True,
                auto_categorize=False,
            ),
        )
        opened += 1
    return opened


async def _balances_as_of(
    session: AsyncSession, budget_id: UUID, as_of: date
) -> dict[UUID, Decimal]:
    rows = await session.execute(
        select(Transaction.account_id, func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.budget_id == budget_id, Transaction.date <= as_of, BALANCE_ROW)
        .group_by(Transaction.account_id)
    )
    return {account_id: Decimal(str(total)) for account_id, total in rows.all()}


async def _trim_position_history(session: AsyncSession, budget_id: UUID, as_of: date) -> None:
    """Assets and liabilities keep their newest recorded position and lose
    everything behind it — the same trade an account makes when its register
    becomes one Starting Balance row.

    Not "delete them all": an asset's value and an unmanaged liability's
    balance are read newest-first from these rows, so clearing them would
    silently restate the copy's net worth. The newest row may be dated after
    `as_of`; it stays, because it is the position the person most recently
    stated and an older one would be a figure nobody measured.
    """
    for model, owner_column, owner_table in (
        (AssetValueSnapshot, AssetValueSnapshot.asset_id, "assets"),
        (LiabilityBalanceSnapshot, LiabilityBalanceSnapshot.liability_id, "liabilities"),
    ):
        owner = Base.metadata.tables[owner_table]
        mine = select(owner.c.id).where(owner.c.budget_id == budget_id)
        newer = aliased(model)
        newer_owner = getattr(newer, owner_column.key)
        # "A newer row exists for the same owner" — (date, id) so two rows on
        # one day still order, rather than both surviving or both going.
        has_newer = (
            select(newer.id)
            .where(
                newer_owner == owner_column,
                tuple_(newer.date, newer.id) > tuple_(model.date, model.id),
            )
            .exists()
        )
        await session.execute(delete(model).where(owner_column.in_(mine), has_newer))
