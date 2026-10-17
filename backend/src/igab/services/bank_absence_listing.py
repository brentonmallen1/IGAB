"""Which rows the bank stopped reporting the person still needs to hear about.

The listing behind the accounts page's "No longer at the bank" finding, and
the check its Restore and Delete actions run before they act — one query, so
the two can never disagree about which rows are listed. The rule itself is
`domain.bank_absence.is_open`; this gathers its inputs.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import ChangeLog, Transaction
from igab.domain.bank_absence import REMOVED, Absence, RowNow, is_open, latest_by_row
from igab.repositories.sync_run_repo import SyncRunRepository
from igab.repositories.txn_filters import NOT_DELETED


@dataclass(frozen=True)
class OpenAbsence:
    entry: Absence
    row: Transaction
    state: RowNow
    #: For a removed hold: the change-log batch its removal landed in — the
    #: run's — which is what Restore takes the row's delete back from.
    removal_batch_id: uuid.UUID | None = None


async def open_absences(session: AsyncSession, budget_id: uuid.UUID) -> list[OpenAbsence]:
    """Rows recent runs found missing from the feed that are still news,
    ordered by account and date."""
    latest = latest_by_row(await SyncRunRepository(session).recent_absences(budget_id))
    if not latest:
        return []
    rows = {
        t.id: t
        for t in (
            await session.execute(
                select(Transaction).where(
                    Transaction.budget_id == budget_id, Transaction.id.in_(list(latest))
                )
            )
        ).scalars()
    }

    # The newest system delete of each removed hold: whether it is still in
    # force, and which batch to take it back from. The newest, because a row
    # restored, then re-armed by ⌘Z and removed again, has two.
    removed = [i for i, e in latest.items() if e.action == REMOVED]
    removals: dict[uuid.UUID, ChangeLog] = {}
    if removed:
        for change in (
            await session.execute(
                select(ChangeLog)
                .where(
                    ChangeLog.budget_id == budget_id,
                    ChangeLog.entity_type == "transaction",
                    ChangeLog.entity_id.in_(removed),
                    ChangeLog.action == "delete",
                    ChangeLog.source == "system",
                )
                .order_by(ChangeLog.seq)
            )
        ).scalars():
            removals[change.entity_id] = change

    # Bank ids a live row carries now, per account: a hold the bank reports
    # again came back as a fresh row, and is not missing any more.
    wanted = {e.sync_id for e in latest.values() if e.sync_id}
    live: dict[uuid.UUID, set[str]] = {}
    if wanted:
        for account_id, sync_id in (
            await session.execute(
                select(Transaction.account_id, Transaction.sync_id).where(
                    Transaction.budget_id == budget_id,
                    NOT_DELETED,
                    Transaction.sync_id.in_(wanted),
                )
            )
        ).all():
            live.setdefault(account_id, set()).add(sync_id)

    out: list[OpenAbsence] = []
    for txn_id, entry in latest.items():
        row = rows.get(txn_id)
        if row is None:
            continue
        removal = removals.get(txn_id)
        state = RowNow(
            is_deleted=row.is_deleted,
            sync_id=row.sync_id,
            cleared=row.cleared,
            removal_undone=removal is None or removal.undone_at is not None,
        )
        if not is_open(entry, state, live.get(entry.account_id, set())):
            continue
        out.append(
            OpenAbsence(
                entry=entry,
                row=row,
                state=state,
                removal_batch_id=removal.batch_id if removal is not None else None,
            )
        )
    out.sort(key=lambda a: (str(a.entry.account_id), a.entry.date, str(a.entry.transaction_id)))
    return out
