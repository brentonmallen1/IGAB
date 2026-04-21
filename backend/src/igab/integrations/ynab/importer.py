import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Category, CategoryGroup
from igab.integrations.ynab.models import YNABBudget
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.transaction_service import TransactionCreate, TransactionService

_TRANSFER_PREFIX = "Transfer : "
_YNAB_INFLOW_GROUP = "Inflow"
_SYSTEM_INCOME_GROUP = "Income"


@dataclass
class ImportResult:
    accounts_imported: int = 0
    category_groups_imported: int = 0
    categories_imported: int = 0
    transactions_imported: int = 0
    transactions_skipped: int = 0
    assignments_imported: int = 0
    errors: list[str] = field(default_factory=list)


class YNABImporter:
    def __init__(
        self,
        session: AsyncSession,
        budget_id: uuid.UUID,
        account_repo: AccountRepository,
        category_group_repo: CategoryGroupRepository,
        category_repo: CategoryRepository,
        payee_repo: PayeeRepository,
        transaction_repo: TransactionRepository,
        transaction_service: TransactionService,
        assignment_repo: BudgetAssignmentRepository,
    ) -> None:
        self.session = session
        self.budget_id = budget_id
        self.account_repo = account_repo
        self.category_group_repo = category_group_repo
        self.category_repo = category_repo
        self.payee_repo = payee_repo
        self.transaction_repo = transaction_repo
        self.transaction_service = transaction_service
        self.assignment_repo = assignment_repo
        # name → Account
        self._account_cache: dict[str, Account] = {}
        # group name → CategoryGroup
        self._group_cache: dict[str, CategoryGroup] = {}
        # (group_id, category name lower) → Category
        self._category_cache: dict[tuple[uuid.UUID, str], Category] = {}

    async def import_budget(self, budget: YNABBudget) -> ImportResult:
        result = ImportResult()
        await self._import_transactions(budget, result)
        await self._import_assignments(budget, result)
        return result

    async def _get_or_create_account(self, name: str, result: ImportResult) -> Account:
        if name in self._account_cache:
            return self._account_cache[name]

        row = await self.session.execute(
            select(Account).where(
                Account.budget_id == self.budget_id,
                func.lower(Account.name) == name.lower(),
                Account.is_deleted == False,  # noqa: E712
            )
        )
        account = row.scalar_one_or_none()
        if account is None:
            account = await self.account_repo.create(
                budget_id=self.budget_id,
                name=name,
                account_type="checking",
                on_budget=True,
            )
            result.accounts_imported += 1

        self._account_cache[name] = account
        return account

    async def _get_or_create_category(
        self, group_name: str, category_name: str, result: ImportResult
    ) -> Category:
        # Map YNAB's "Inflow" category group to the system "Income" group
        if group_name == _YNAB_INFLOW_GROUP:
            group_name = _SYSTEM_INCOME_GROUP

        if group_name not in self._group_cache:
            row = await self.session.execute(
                select(CategoryGroup).where(
                    CategoryGroup.budget_id == self.budget_id,
                    func.lower(CategoryGroup.name) == group_name.lower(),
                    CategoryGroup.is_deleted == False,  # noqa: E712
                )
            )
            group = row.scalar_one_or_none()
            if group is None:
                group = await self.category_group_repo.create(
                    budget_id=self.budget_id,
                    name=group_name,
                    is_system=(group_name == _SYSTEM_INCOME_GROUP),
                )
                result.category_groups_imported += 1
            self._group_cache[group_name] = group

        group = self._group_cache[group_name]
        cache_key = (group.id, category_name.lower())

        if cache_key not in self._category_cache:
            row = await self.session.execute(
                select(Category).where(
                    Category.category_group_id == group.id,
                    func.lower(Category.name) == category_name.lower(),
                    Category.is_deleted == False,  # noqa: E712
                )
            )
            category = row.scalar_one_or_none()
            if category is None:
                category = await self.category_repo.create(
                    budget_id=self.budget_id,
                    category_group_id=group.id,
                    name=category_name,
                )
                result.categories_imported += 1
            self._category_cache[cache_key] = category

        return self._category_cache[cache_key]

    async def _import_transactions(self, budget: YNABBudget, result: ImportResult) -> None:
        # Separate non-transfer and transfer transactions
        regular_rows: list[dict] = []
        transfer_txns = []

        # Batch-resolve all non-transfer payee names upfront
        non_transfer_payees = {
            txn.payee
            for txn in budget.transactions
            if txn.payee and not txn.payee.startswith(_TRANSFER_PREFIX)
        }
        payee_map = await self.payee_repo.find_or_create_batch(
            self.budget_id, list(non_transfer_payees)
        )

        for txn in budget.transactions:
            try:
                account = await self._get_or_create_account(txn.account_name, result)

                category_id: uuid.UUID | None = None
                if txn.category_group and txn.category:
                    cat = await self._get_or_create_category(
                        txn.category_group, txn.category, result
                    )
                    category_id = cat.id

                if txn.payee.startswith(_TRANSFER_PREFIX):
                    # Defer transfers — need both account IDs to link them
                    if txn.amount >= 0:
                        result.transactions_skipped += 1
                        continue
                    transfer_txns.append((txn, account, category_id))
                else:
                    payee_id = payee_map.get(txn.payee) if txn.payee else None
                    regular_rows.append(
                        {
                            "id": uuid.uuid4(),
                            "budget_id": self.budget_id,
                            "account_id": account.id,
                            "date": txn.date,
                            "amount": txn.amount,
                            "payee_id": payee_id,
                            "category_id": category_id,
                            "memo": txn.memo or None,
                            "cleared": txn.cleared,
                            "approved": True,
                            "is_split": False,
                            "is_deleted": False,
                        }
                    )

            except Exception as e:
                result.errors.append(f"Transaction {txn.date} {txn.payee}: {e}")
                result.transactions_skipped += 1

        # Bulk insert regular transactions
        inserted = await self.transaction_repo.bulk_create(regular_rows)
        result.transactions_imported += inserted

        # Handle transfers individually (they need paired linking via TransactionService)
        for txn, account, category_id in transfer_txns:
            try:
                target_name = txn.payee[len(_TRANSFER_PREFIX) :]
                target_account = await self._get_or_create_account(target_name, result)
                data = TransactionCreate(
                    account_id=account.id,
                    date=txn.date,
                    amount=txn.amount,
                    memo=txn.memo,
                    cleared=txn.cleared,
                    approved=True,
                    transfer_account_id=target_account.id,
                )
                await self.transaction_service.create(self.budget_id, data)
                result.transactions_imported += 1
            except Exception as e:
                result.errors.append(f"Transfer {txn.date} {txn.payee}: {e}")
                result.transactions_skipped += 1

    async def _import_assignments(self, budget: YNABBudget, result: ImportResult) -> None:
        for entry in budget.budget_entries:
            try:
                cat = await self._get_or_create_category(
                    entry.category_group, entry.category, result
                )
                assignment = await self.assignment_repo.get_or_create(
                    self.budget_id, cat.id, entry.month
                )
                await self.assignment_repo.update(assignment.id, assigned=entry.assigned)
                result.assignments_imported += 1
            except Exception as e:
                result.errors.append(f"Assignment {entry.month} {entry.category}: {e}")
