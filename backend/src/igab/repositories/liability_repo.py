import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import not_, select

from igab.db.models import Account, Liability, LiabilityBalanceSnapshot
from igab.repositories.base import BaseRepository

#: A loan whose account the user has closed.
#:
#: The importer attaches a companion Liability to every liability-classified
#: account it creates, including the ones someone ticked "import & close" on —
#: so a YNAB import of a paid-off car loan produced a closed account nobody
#: could see and a live loan in the sidebar, the Liabilities overview, both
#: Guide planners and the liabilities report. Reported as "all my previous
#: loans that I did import and close are still showing up".
#:
#: The rule is not new here; `DELETE /liabilities/{id}` already reasons that a
#: closed account "has no register left to feed the liability, so the liability
#: may go". This is the listing side of the same sentence.
#:
#: EXISTS rather than a join or `linked_account_id NOT IN (...)`: an UNMANAGED
#: liability has no linked account at all, and `NULL IN (non-empty set)` is
#: UNKNOWN, whose negation is UNKNOWN — which would silently drop exactly the
#: rows that have no account to be closed. Same trap `IN_SYSTEM_GROUP`
#: documents.
UNDER_CLOSED_ACCOUNT = (
    select(Account.id)
    .where(
        Account.id == Liability.linked_account_id,
        Account.is_closed == True,  # noqa: E712
    )
    .correlate(Liability)
    .exists()
)


class LiabilityRepository(BaseRepository[Liability]):
    model = Liability

    async def get_all(
        self, budget_id: uuid.UUID, *, include_closed: bool = False
    ) -> list[Liability]:
        """Live liabilities. A loan under a closed account is out by default.

        Default-out rather than opt-out, because every reader of this list is
        asking "what do I still owe": the sidebar, the Liabilities overview,
        the payoff planner, the pay-down-or-save tool, the liabilities report
        and the Guide's card-utilization check. A settled loan belongs in none
        of them.
        """
        q = select(Liability).where(
            Liability.budget_id == budget_id,
            Liability.is_deleted == False,  # noqa: E712
        )
        if not include_closed:
            q = q.where(not_(UNDER_CLOSED_ACCOUNT))
        result = await self.session.execute(q.order_by(Liability.name))
        return list(result.scalars().all())

    async def get_by_linked_account(self, account_id: uuid.UUID) -> Liability | None:
        result = await self.session.execute(
            select(Liability).where(
                Liability.linked_account_id == account_id,
                Liability.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_snapshots(self, liability_id: uuid.UUID) -> list[LiabilityBalanceSnapshot]:
        result = await self.session.execute(
            select(LiabilityBalanceSnapshot)
            .where(LiabilityBalanceSnapshot.liability_id == liability_id)
            .order_by(LiabilityBalanceSnapshot.date)
        )
        return list(result.scalars().all())

    async def upsert_snapshot(
        self,
        liability_id: uuid.UUID,
        snapshot_date: date,
        balance: Decimal,
        source: str = "manual",
    ) -> LiabilityBalanceSnapshot:
        """One snapshot per day: a second entry for the same date replaces it."""
        result = await self.session.execute(
            select(LiabilityBalanceSnapshot).where(
                LiabilityBalanceSnapshot.liability_id == liability_id,
                LiabilityBalanceSnapshot.date == snapshot_date,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.balance = balance
            existing.source = source
            await self.session.flush()
            return existing
        snapshot = LiabilityBalanceSnapshot(
            liability_id=liability_id, date=snapshot_date, balance=balance, source=source
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot
