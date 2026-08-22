import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select, update

from igab.db.models import (
    Account,
    Category,
    Liability,
    LiabilityBalanceSnapshot,
    Transaction,
)
from igab.repositories.base import BaseRepository

LiabilityDisposition = Literal["keep", "delete"]

#: Account type → the unmanaged liability kind that means the same thing.
#: Needed only when an account is deleted: its companion stops being able to
#: read a kind off the account and has to carry one itself again. Anything not
#: listed — the generic loan, other_liability, a custom type — becomes 'other',
#: which is what the unmanaged vocabulary has for "a debt".
_UNMANAGED_KIND: dict[str, str] = {
    "mortgage": "mortgage",
    "auto_loan": "auto",
    "student_loan": "student",
    "credit_card": "credit_card",
}


class AccountRepository(BaseRepository[Account]):
    model = Account

    async def get_all(self, budget_id: uuid.UUID, include_closed: bool = False) -> list[Account]:
        q = select(Account).where(
            Account.budget_id == budget_id,
            Account.is_deleted == False,  # noqa: E712
        )
        if not include_closed:
            q = q.where(Account.is_closed == False)  # noqa: E712
        q = q.order_by(Account.sort_order, Account.name)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def get_balance(self, account_id: uuid.UUID) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared != "pending",
            )
        )
        return result.scalar_one()

    async def get_cleared_balance(self, account_id: uuid.UUID) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared.in_(["cleared", "reconciled"]),
            )
        )
        return result.scalar_one()

    async def get_uncategorized_count(self, account_id: uuid.UUID) -> int:
        # Leaf rows: split parents legitimately have no category, while an
        # uncategorized split child is a real gap the user should fill.
        # Transfer legs whose partner account is OFF-budget are spending and
        # need a category too; on-budget↔on-budget legs never do.
        from sqlalchemy import or_
        from sqlalchemy.orm import aliased

        # Off-budget accounts don't use categories at all — the categorized
        # side of a spending transfer lives on the on-budget leg, and plain
        # rows here are net-worth movement, not unfiled spending.
        account = await self.get(account_id)
        if account is None or not account.on_budget:
            return 0

        partner = aliased(Transaction)
        partner_account = aliased(Account)
        result = await self.session.execute(
            select(func.count(Transaction.id))
            .select_from(Transaction)
            .outerjoin(partner, Transaction.transfer_id == partner.id)
            .outerjoin(partner_account, partner.account_id == partner_account.id)
            .where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.is_split == False,  # noqa: E712
                Transaction.category_id.is_(None),
                Transaction.cleared != "pending",
                or_(
                    Transaction.transfer_id.is_(None),
                    partner_account.on_budget == False,  # noqa: E712
                ),
            )
        )
        return result.scalar_one()

    async def get_on_budget(self, budget_id: uuid.UUID) -> list[Account]:
        result = await self.session.execute(
            select(Account).where(
                Account.budget_id == budget_id,
                Account.on_budget == True,  # noqa: E712
                Account.is_deleted == False,  # noqa: E712
                Account.is_closed == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def soft_delete(
        self, id: uuid.UUID, *, liability_disposition: LiabilityDisposition = "keep"
    ) -> None:
        """Remove the account, and decide what becomes of the debt it tracked.

        `keep` (the default, and the non-destructive branch) converts the
        companion liability from managed to unmanaged: the debt still exists,
        so it keeps its APR, its payment history and its balance, and only
        stops deriving that balance from a ledger that is going away. `delete`
        removes both.

        The balance has to be frozen BEFORE the transactions are soft-deleted —
        an unmanaged liability reads `manual_balance`, and computing it after
        would freeze a zero.
        """
        frozen_balance: Decimal | None = None
        history: list[tuple[date, Decimal]] = []
        companion = (
            await self.session.execute(
                select(Liability).where(
                    Liability.linked_account_id == id,
                    Liability.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if companion is not None and liability_disposition == "keep":
            frozen_balance = max(Decimal("0"), -(await self.get_balance(id)))
            history = await self._owed_history(id)

        await self.session.execute(
            update(Transaction)
            .where(Transaction.account_id == id, Transaction.is_deleted == False)  # noqa: E712
            .values(is_deleted=True)
        )
        # The FK's ON DELETE SET NULL only fires on hard deletes; a soft-deleted
        # account must not leave its CC-payment category pointing at it.
        await self.session.execute(
            update(Category).where(Category.linked_account_id == id).values(linked_account_id=None)
        )

        if companion is not None:
            if liability_disposition == "delete":
                companion.is_deleted = True
            else:
                companion.linked_account_id = None
                companion.manual_balance = frozen_balance
                # Carry the curve across, not just today's number. Net worth
                # HISTORY reads an unmanaged liability from its snapshots, and
                # a converted one has none — so without this the debt vanishes
                # from every past point while today's stays right, drawing a
                # cliff into the chart that never happened. `manual_balance`
                # alone only fixes the latest point.
                # A liability that was unmanaged before it was linked may still
                # hold snapshots of its own, and (liability_id, date) is
                # unique — its own record wins over a reconstructed one.
                existing_dates = set(
                    (
                        await self.session.execute(
                            select(LiabilityBalanceSnapshot.date).where(
                                LiabilityBalanceSnapshot.liability_id == companion.id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for point_date, owed in history:
                    if point_date in existing_dates:
                        continue
                    self.session.add(
                        LiabilityBalanceSnapshot(
                            liability_id=companion.id,
                            date=point_date,
                            balance=owed,
                            source="initial",
                        )
                    )
                # An unmanaged liability has to answer "what kind of debt?" on
                # its own now — the account that was answering is going.
                # Derived from the account, NOT from whatever the column
                # happens to hold: while linked, that value was ignored by
                # definition, so it is not evidence of anything. Companions
                # created by the c1d9f4b26a83 backfill carry a coarse 'other'
                # from before the kind became derived — preferring it would
                # turn a mortgage into "Other" on the way out. The stored value
                # is the fallback only when there is no account left to ask.
                account = await self.get(id)
                derived = _UNMANAGED_KIND.get(account.account_type, "other") if account else None
                companion.liability_type = derived or companion.liability_type or "other"
            await self.session.flush()

        await super().soft_delete(id)

    async def _owed_history(self, account_id: uuid.UUID) -> list[tuple[date, Decimal]]:
        """Monthly owed-balance points for a liability account's whole ledger.

        Mirrors LiabilityService.get_balance_history's managed branch — same
        monthly cumulation, same negation, same floor at zero — so a converted
        liability's chart is the one the account was already drawing. Read
        through TransactionRepository rather than reimplemented, because
        "how much did this account move this month" has PARENT_ROW and POSTED
        semantics that must not drift between the two.

        Months with no activity are skipped: the snapshot lookup is a step
        function that holds the last value, so a gap is not a hole.
        """
        from igab.repositories.transaction_repo import TransactionRepository

        by_month = await TransactionRepository(self.session).sum_by_account_by_month(
            account_id, end_date=date.today()
        )
        points: list[tuple[date, Decimal]] = []
        running = Decimal("0")
        for month in sorted(by_month):
            running += by_month[month]
            points.append((month, max(Decimal("0"), -running)))
        return points

    async def get_by_simplefin_id(self, budget_id: uuid.UUID, simplefin_id: str) -> Account | None:
        result = await self.session.execute(
            select(Account).where(
                Account.budget_id == budget_id,
                Account.simplefin_account_id == simplefin_id,
                Account.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_linked_simplefin_accounts(self, budget_id: uuid.UUID) -> list[Account]:
        result = await self.session.execute(
            select(Account).where(
                Account.budget_id == budget_id,
                Account.simplefin_account_id.isnot(None),
                Account.is_deleted == False,  # noqa: E712
                Account.is_closed == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def get_sync_status(self, budget_id: uuid.UUID) -> list[Account]:
        """Return all accounts with SimpleFIN link info for sidebar status display."""
        result = await self.session.execute(
            select(Account).where(
                Account.budget_id == budget_id,
                Account.simplefin_account_id.isnot(None),
                Account.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())
