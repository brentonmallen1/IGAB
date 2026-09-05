import uuid
from datetime import UTC
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, ReconciliationSnapshot, Transaction
from igab.domain.payee_names import RECONCILIATION_ADJUSTMENT_PAYEE
from igab.repositories.account_repo import AccountRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_filters import BALANCE_ROW, CLEARED, not_future
from igab.services.transaction_service import TransactionCreate, TransactionService
from igab.utils.clock import today_utc


class ReconciliationService:
    def __init__(
        self,
        session: AsyncSession,
        repo: ReconciliationRepository,
        account_repo: AccountRepository,
        payee_repo: PayeeRepository,
        transaction_repo: TransactionRepository,
        transaction_service: TransactionService,
    ) -> None:
        self.session = session
        self.repo = repo
        self.account_repo = account_repo
        self.payee_repo = payee_repo
        self.transaction_repo = transaction_repo
        self.transaction_service = transaction_service

    async def get_status(self, account_id: uuid.UUID) -> dict:
        """Return current cleared balance and uncleared transaction count for the account.

        Future-dated transactions are excluded everywhere: a bank statement
        can only reflect what has already happened, so a future-dated cleared
        transaction would skew the cleared balance and manufacture a bogus
        adjustment against the statement.
        """
        from sqlalchemy import func

        as_of = today_utc()

        cleared_result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == account_id,
                BALANCE_ROW,
                CLEARED,
                not_future(as_of),
            )
        )
        cleared_balance = Decimal(str(cleared_result.scalar_one()))

        uncleared_result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared == "uncleared",
                Transaction.date <= as_of,
            )
        )
        uncleared_count = uncleared_result.scalar_one()

        pending_result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared == "pending",
                Transaction.date <= as_of,
            )
        )
        pending_count = pending_result.scalar_one()

        return {
            "cleared_balance": cleared_balance,
            "uncleared_count": uncleared_count,
            "pending_count": pending_count,
        }

    async def create_adjustment(
        self,
        account_id: uuid.UUID,
        adjustment_amount: Decimal,
    ) -> Transaction:
        """Create a cleared adjustment transaction to bring the account into balance."""

        account = await self.account_repo.get_or_raise(account_id)
        payee = await self.payee_repo.find_or_create(
            account.budget_id, RECONCILIATION_ADJUSTMENT_PAYEE
        )
        # Through the service, not the repo: an adjustment moves real money
        # and belongs in the change log like any other transaction, so the
        # user can undo it. Left uncategorized on purpose — on a budget
        # account that lands the difference in Ready to Assign.
        return await self.transaction_service.create(
            account.budget_id,
            TransactionCreate(
                account_id=account_id,
                date=today_utc(),
                amount=adjustment_amount,
                payee_id=payee.id,
                category_id=None,
                memo="Entered automatically by IGAB",
                cleared="cleared",
                approved=True,
                auto_categorize=False,
            ),
        )

    async def finish(
        self,
        account_id: uuid.UUID,
        statement_balance: Decimal,
        adjustment_transaction_id: uuid.UUID | None = None,
    ) -> ReconciliationSnapshot:
        """Mark all cleared transactions as reconciled and save a snapshot.

        The cleared balance is recomputed HERE (not trusted from the UI): any
        transaction that slipped in between the status call and finish would
        otherwise be silently swept into a reconciliation that doesn't match
        the statement. If the recomputed balance still differs, an adjustment
        transaction is created automatically so reconciliation always locks
        an account that agrees with the bank statement.
        """
        status = await self.get_status(account_id)
        cleared_balance = status["cleared_balance"]

        difference = statement_balance - cleared_balance
        if difference != 0:
            adjustment = await self.create_adjustment(account_id, difference)
            adjustment_transaction_id = adjustment.id

        # Mark all cleared → reconciled (includes the fresh adjustment).
        # Future-dated cleared transactions stay merely "cleared": they were
        # excluded from the balance above, so locking them as reconciled
        # would bless amounts the statement never confirmed.
        await self.session.execute(
            update(Transaction)
            .where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.cleared == "cleared",
                Transaction.date <= today_utc(),
            )
            .values(cleared="reconciled")
        )

        # Update account reconciliation metadata
        from datetime import datetime

        await self.session.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(
                last_reconciled_at=datetime.now(tz=UTC),
                last_reconciled_balance=statement_balance,
            )
        )

        snapshot = await self.repo.create(
            account_id=account_id,
            statement_balance=statement_balance,
            cleared_balance=cleared_balance,
            adjustment_amount=difference,
            adjustment_transaction_id=adjustment_transaction_id,
        )
        await self.session.flush()
        return snapshot

    async def get_history(self, account_id: uuid.UUID) -> list[ReconciliationSnapshot]:
        return await self.repo.get_history(account_id)
