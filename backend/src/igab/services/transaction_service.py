from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Payee, Transaction
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository


@dataclass
class TransactionCreate:
    account_id: uuid.UUID
    date: date
    amount: Decimal
    payee_id: uuid.UUID | None = None
    payee_name: str | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    cleared: str = "uncleared"
    approved: bool = True
    transfer_account_id: uuid.UUID | None = None
    parent_transaction_id: uuid.UUID | None = None
    import_id: str | None = None
    import_batch_id: uuid.UUID | None = None


@dataclass
class TransactionUpdate:
    date: date | None = None
    amount: Decimal | None = None
    payee_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    memo: str | None = None
    cleared: str | None = None
    approved: bool | None = None


class TransactionService:
    def __init__(
        self,
        session: AsyncSession,
        transaction_repo: TransactionRepository,
        account_repo: AccountRepository,
        category_repo: CategoryRepository,
        payee_repo: PayeeRepository,
    ) -> None:
        self.session = session
        self.transaction_repo = transaction_repo
        self.account_repo = account_repo
        self.category_repo = category_repo
        self.payee_repo = payee_repo

    async def create(
        self, budget_id: uuid.UUID, data: TransactionCreate
    ) -> Transaction:
        account = await self.account_repo.get_or_raise(data.account_id)
        if str(account.budget_id) != str(budget_id):
            raise InvariantViolation("Account does not belong to this budget")

        if data.transfer_account_id:
            return await self._create_transfer(budget_id, data)

        # Resolve or create payee
        payee = await self._resolve_payee(budget_id, data)
        payee_id = payee.id if payee else None

        # Apply payee default category when none provided (auto-categorization memory)
        category_id = data.category_id
        if payee and not category_id and payee.default_category_id:
            category_id = payee.default_category_id

        # Update payee default category memory when user explicitly sets one
        if payee_id and data.category_id:
            await self.payee_repo.update(payee_id, default_category_id=data.category_id)

        txn = await self.transaction_repo.create(
            budget_id=budget_id,
            account_id=data.account_id,
            date=data.date,
            amount=data.amount,
            payee_id=payee_id,
            category_id=category_id,
            memo=data.memo,
            cleared=data.cleared,
            approved=data.approved,
            parent_transaction_id=data.parent_transaction_id,
            import_id=data.import_id,
            import_batch_id=data.import_batch_id,
        )
        return txn

    async def create_split(
        self, budget_id: uuid.UUID, header: TransactionCreate, splits: list[TransactionCreate]
    ) -> Transaction:
        """Create a split transaction: one parent + N children."""
        total = sum(s.amount for s in splits)
        if abs(total - header.amount) > Decimal("0.001"):
            raise InvariantViolation(
                f"Split amounts {total} do not sum to transaction amount {header.amount}"
            )

        # Parent has no category (it's distributed across splits)
        header.category_id = None
        parent = await self.create(budget_id, header)
        await self.transaction_repo.update(parent.id, is_split=True)

        for split in splits:
            split.parent_transaction_id = parent.id
            split.account_id = header.account_id
            split.date = header.date
            await self.create(budget_id, split)

        await self.session.refresh(parent)
        return parent

    async def update(
        self, budget_id: uuid.UUID, transaction_id: uuid.UUID, data: TransactionUpdate
    ) -> Transaction:
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        if txn.cleared == "reconciled":
            raise InvariantViolation("Cannot edit a reconciled transaction")

        changes = {k: v for k, v in vars(data).items() if v is not None}

        # If updating transfer's amount, also update the paired transaction
        if "amount" in changes and txn.transfer_id:
            paired_amount = -changes["amount"]
            await self.transaction_repo.update(txn.transfer_id, amount=paired_amount)

        return await self.transaction_repo.update(transaction_id, **changes)

    async def delete(self, budget_id: uuid.UUID, transaction_id: uuid.UUID) -> None:
        txn = await self.transaction_repo.get_or_raise(transaction_id)
        if str(txn.budget_id) != str(budget_id):
            raise InvariantViolation("Transaction does not belong to this budget")
        if txn.cleared == "reconciled":
            raise InvariantViolation("Cannot delete a reconciled transaction")

        # Soft delete transfer partner too
        if txn.transfer_id:
            await self.transaction_repo.soft_delete(txn.transfer_id)

        # Soft delete any splits
        splits = await self.transaction_repo.get_splits(transaction_id)
        for split in splits:
            await self.transaction_repo.soft_delete(split.id)

        await self.transaction_repo.soft_delete(transaction_id)

    async def _create_transfer(
        self, budget_id: uuid.UUID, data: TransactionCreate
    ) -> Transaction:
        to_account = await self.account_repo.get_or_raise(data.transfer_account_id)

        # Source: outflow from from-account
        from_payee = await self._get_transfer_payee(budget_id, to_account.name)
        source = await self.transaction_repo.create(
            budget_id=budget_id,
            account_id=data.account_id,
            date=data.date,
            amount=-abs(data.amount),
            payee_id=from_payee.id,
            category_id=None,
            memo=data.memo,
            cleared=data.cleared,
            approved=data.approved,
        )

        # Destination: inflow into to-account
        from_account = await self.account_repo.get_or_raise(data.account_id)
        to_payee = await self._get_transfer_payee(budget_id, from_account.name)
        dest = await self.transaction_repo.create(
            budget_id=budget_id,
            account_id=data.transfer_account_id,
            date=data.date,
            amount=abs(data.amount),
            payee_id=to_payee.id,
            category_id=None,
            memo=data.memo,
            cleared="uncleared",
            approved=data.approved,
            transfer_id=source.id,
        )

        # Link source → dest
        await self.transaction_repo.update(source.id, transfer_id=dest.id)
        await self.session.refresh(source)
        return source

    async def _get_transfer_payee(self, budget_id: uuid.UUID, account_name: str):
        name = f"Transfer : {account_name}"
        return await self.payee_repo.find_or_create(budget_id, name)

    async def _resolve_payee(
        self, budget_id: uuid.UUID, data: TransactionCreate
    ) -> Payee | None:
        if data.payee_id:
            result = await self.session.get(Payee, data.payee_id)
            return result
        if data.payee_name:
            return await self.payee_repo.find_or_create(budget_id, data.payee_name)
        return None
