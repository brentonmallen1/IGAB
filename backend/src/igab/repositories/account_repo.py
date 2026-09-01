import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import and_, case, func, not_, select, update

from igab.db.models import (
    Account,
    Category,
    Liability,
    LiabilityBalanceSnapshot,
    Transaction,
)
from igab.repositories.base import BaseRepository
from igab.repositories.txn_filters import (
    BALANCE_ROW,
    CARD_ACCOUNT,
    CASH_ACCOUNT,
    CLEARED,
    NEEDS_CATEGORY,
    NOT_DELETED,
    PARENT_ROW,
    POSTED,
    not_future,
)

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

    async def _sums_by_account(
        self, account_ids: Sequence[uuid.UUID], *predicates: Any
    ) -> dict[uuid.UUID, Decimal]:
        """One grouped aggregate for many accounts, over `predicates`.

        The listing endpoint asked per account in a Python loop — three
        queries each, so sixteen accounts cost forty-nine round-trips and the
        cost grew with the account count. The predicates are the same shared
        constants either way, so the rule still has one home; only the number
        of statements changes.

        Every requested id appears in the result: an account with no matching
        rows contributes no group, and a missing key would read as "unknown"
        where the answer is zero.
        """
        if not account_ids:
            return {}
        result = await self.session.execute(
            select(
                Transaction.account_id,
                func.coalesce(func.sum(Transaction.amount), 0),
            )
            .where(Transaction.account_id.in_(account_ids), *predicates)
            .group_by(Transaction.account_id)
        )
        sums = {account_id: total for account_id, total in result.all()}
        return {account_id: sums.get(account_id, Decimal("0")) for account_id in account_ids}

    async def balances_for(self, account_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
        return await self._sums_by_account(account_ids, BALANCE_ROW)

    async def cleared_balances_for(
        self, account_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Decimal]:
        return await self._sums_by_account(account_ids, BALANCE_ROW, CLEARED)

    async def uncategorized_counts_for(
        self, account_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Unfiled leaf rows per account.

        No on-budget check here or in the caller: `NEEDS_CATEGORY` already
        carries `ON_BUDGET_ACCOUNT`, so an off-budget account matches no rows
        and lands on the zero default — which is what the per-account version
        spent an extra SELECT to discover.
        """
        if not account_ids:
            return {}
        result = await self.session.execute(
            select(Transaction.account_id, func.count(Transaction.id))
            .select_from(Transaction)
            .where(
                Transaction.account_id.in_(account_ids),
                NOT_DELETED,
                POSTED,
                NEEDS_CATEGORY,
            )
            .group_by(Transaction.account_id)
        )
        counts = {account_id: n for account_id, n in result.all()}
        return {account_id: counts.get(account_id, 0) for account_id in account_ids}

    async def get_balance(self, account_id: uuid.UUID) -> Decimal:
        return (await self.balances_for([account_id]))[account_id]

    async def get_cleared_balance(self, account_id: uuid.UUID) -> Decimal:
        """The confirmed part of `get_balance`, over the same rows.

        No date cutoff, on purpose: this is one term of the header's
        partition (balance = cleared + uncleared), and cutting only this term
        would relabel a future-dated cleared row as uncleared rather than
        excluding it. Reconciliation asks a narrower question and adds
        `not_future` itself — see that function for why the two differ.
        """
        return (await self.cleared_balances_for([account_id]))[account_id]

    async def get_uncategorized_count(self, account_id: uuid.UUID) -> int:
        # Leaf rows: split parents legitimately have no category, while an
        # uncategorized split child is a real gap the user should fill.
        # Transfer legs whose partner account is OFF-budget are spending and
        # need a category too; on-budget↔on-budget legs never do.
        # Off-budget accounts don't use categories at all — the categorized
        # side of a spending transfer lives on the on-budget leg, and plain
        # rows here are net-worth movement, not unfiled spending.
        # Was a hand-rolled partner join reading `transfer_id IS NULL`, which
        # counted an unpaired transfer leg as unfiled. NEEDS_CATEGORY reaches
        # the counterpart through the transfer payee as well as the link, so a
        # leg whose partner never imported is still recognised as a transfer.
        return (await self.uncategorized_counts_for([account_id]))[account_id]

    async def sum_on_budget_balance(self, budget_id: uuid.UUID, as_of: date) -> Decimal:
        """The budget's cash as of the end of a day — the balance term of
        Ready to Assign.

        Closed accounts are IN. Closing an account moves no money: its
        transactions stay, its categorized history stays in the envelopes, so
        leaving its balance out changed Ready to Assign by exactly that
        balance with no transaction to show for it. The import flow offers to
        close every dormant account, which made this the largest single
        distortion on a real multi-year import.

        Bounded to `as_of` (the viewed month's end). Category activity is
        bounded to the month — a row dated next month reaches no envelope
        until then — so an unbounded balance let a future-dated mortgage
        payment lower today's Ready to Assign with nothing to explain it.
        The account header's working balance is deliberately NOT bounded
        (`get_balance`; see `not_future`): a register shows what it holds.

        Cards are OUT (`CASH_ACCOUNT`): an on-budget liability's debt does
        not net against cash. It lives beside the card's set-aside envelope,
        and the only way a card moves Ready to Assign is money assigned to
        it — see domain/cards.py for the model.
        """
        result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Account.budget_id == budget_id,
                CASH_ACCOUNT,  # carries LIVE_ACCOUNT — deleted accounts out
                BALANCE_ROW,
                not_future(as_of),
            )
        )
        return Decimal(str(result.scalar_one()))

    async def card_balances(self, budget_id: uuid.UUID, as_of: date) -> dict[uuid.UUID, Decimal]:
        """Each card's balance through `as_of` — what is owed, as a negative,
        for the budget's card section. Same predicates and bound as the cash
        sum, so the two partition the on-budget balance exactly. Closed cards
        are IN for the same reason closed cash accounts are: closing moves no
        money. Cards with no rows simply do not appear."""
        result = await self.session.execute(
            select(Transaction.account_id, func.coalesce(func.sum(Transaction.amount), 0))
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Account.budget_id == budget_id,
                CARD_ACCOUNT,  # carries LIVE_ACCOUNT — deleted accounts out
                BALANCE_ROW,
                not_future(as_of),
            )
            .group_by(Transaction.account_id)
        )
        return {account_id: Decimal(str(total)) for account_id, total in result.all()}

    async def card_month_flows(
        self, budget_id: uuid.UUID, month_start: date, month_end: date
    ) -> dict[uuid.UUID, tuple[Decimal, Decimal, Decimal]]:
        """Each card's charges, inflows and still-pending net inside one month,
        as `(charges, inflows, pending)` — charges negative, inflows positive,
        so the first pair sums to the month's move in the balance.

        Same predicates and same upper bound as `card_balances`, one month wide
        instead of open-ended: the two have to agree about which rows count, or
        a month's net would not reconcile against the balances either side of
        it. Cards with no rows that month simply do not appear.

        Deliberately the card's own ledger, not the reserve's legs. `payments`
        is paired transfers from cash; `inflows` here is every credit — refunds,
        rewards, someone else paying the bill, and a payment whose transfer leg
        was never paired. The gap between the two is the diagnostic.

        **`pending` is the named half of a deliberate divergence.** `POSTED`
        keeps provisional rows out of every money aggregate, so this panel and
        the balance beside it agree with each other — and both disagree with
        the register, which shows a pending row the moment the bank mentions
        it. A real card read `charged 2,400` against a register the user
        counted at `2,700`, with nothing on screen accounting for the gap.
        Reporting it is what keeps the divergence bounded rather than silent;
        it is NOT added to the other two, which stay posted-only.

        One query, so the three can never be taken over different row sets:
        the WHERE keeps every live parent row in the month and `POSTED` moves
        into the case expressions.
        """
        charges = func.sum(case((and_(POSTED, Transaction.amount < 0), Transaction.amount), else_=0))
        inflows = func.sum(case((and_(POSTED, Transaction.amount > 0), Transaction.amount), else_=0))
        pending = func.sum(case((not_(POSTED), Transaction.amount), else_=0))
        result = await self.session.execute(
            select(
                Transaction.account_id,
                func.coalesce(charges, 0),
                func.coalesce(inflows, 0),
                func.coalesce(pending, 0),
            )
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Account.budget_id == budget_id,
                CARD_ACCOUNT,
                NOT_DELETED,
                PARENT_ROW,
                Transaction.date >= month_start,
                not_future(month_end),
            )
            .group_by(Transaction.account_id)
        )
        return {
            account_id: (Decimal(str(charged)), Decimal(str(received)), Decimal(str(unposted)))
            for account_id, charged, received, unposted in result.all()
        }

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
