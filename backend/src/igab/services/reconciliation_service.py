import uuid
from datetime import UTC
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, ReconciliationSnapshot, Transaction
from igab.repositories.account_repo import AccountRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.transaction_repo import TransactionRepository


class ReconciliationService:
    def __init__(
        self,
        session: AsyncSession,
        repo: ReconciliationRepository,
        account_repo: AccountRepository,
        payee_repo: PayeeRepository,
        transaction_repo: TransactionRepository,
    ) -> None:
        self.session = session
        self.repo = repo
        self.account_repo = account_repo
        self.payee_repo = payee_repo
        self.transaction_repo = transaction_repo

    async def get_status(self, account_id: uuid.UUID) -> dict:
        """Return current cleared balance and uncleared transaction count for the account."""
        from sqlalchemy import func

        cleared_result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared.in_(["cleared", "reconciled"]),
            )
        )
        cleared_balance = Decimal(str(cleared_result.scalar_one()))

        uncleared_result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared == "uncleared",
            )
        )
        uncleared_count = uncleared_result.scalar_one()

        pending_result = await self.session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
                Transaction.cleared == "pending",
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
        from datetime import date

        account = await self.account_repo.get_or_raise(account_id)
        payee = await self.payee_repo.find_or_create(
            account.budget_id, "Reconciliation Balance Adjustment"
        )
        return await self.transaction_repo.create(
            budget_id=account.budget_id,
            account_id=account_id,
            date=date.today(),
            amount=adjustment_amount,
            payee_id=payee.id,
            category_id=None,
            memo="Entered automatically by IGAB",
            cleared="cleared",
            approved=True,
        )

    async def finish(
        self,
        account_id: uuid.UUID,
        statement_balance: Decimal,
        adjustment_transaction_id: uuid.UUID | None = None,
    ) -> ReconciliationSnapshot:
        """Mark all cleared transactions as reconciled and save a snapshot."""
        status = await self.get_status(account_id)
        cleared_balance = status["cleared_balance"]

        # Mark all cleared → reconciled
        await self.session.execute(
            update(Transaction)
            .where(
                Transaction.account_id == account_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.cleared == "cleared",
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
            adjustment_amount=statement_balance - cleared_balance,
            adjustment_transaction_id=adjustment_transaction_id,
        )
        await self.session.flush()
        return snapshot

    async def get_history(self, account_id: uuid.UUID) -> list[ReconciliationSnapshot]:
        return await self.repo.get_history(account_id)
