import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

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
from igab.services.transaction_service import TransactionService

_TRANSFER_PREFIX = "Transfer : "
_YNAB_INFLOW_GROUP = "Inflow"


def _generate_import_id(account_name: str, txn_date: date, amount: Decimal, payee: str) -> str:
    content = f"{account_name}|{txn_date.isoformat()}|{amount}|{payee}"
    return f"csv:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


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
        account_types: dict[str, tuple[str, bool]] | None = None,
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
        # account name → (account_type, on_budget) override; YNAB register
        # exports carry no type info, so callers may supply the mapping.
        self.account_types = account_types or {}
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
            account_type, on_budget = self.account_types.get(name, ("checking", True))
            account = await self.account_repo.create(
                budget_id=self.budget_id,
                name=name,
                account_type=account_type,
                on_budget=on_budget,
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
        """Import every register row — transfers included — as bulk rows with
        deterministic import_ids (fully idempotent re-import), then link
        transfer legs mutually via ids generated client-side.

        Per-leg cleared/reconciled state from YNAB is preserved. A transfer
        leg carrying a category (YNAB's off-budget spending transfer) imports
        as a plain categorized row and is NOT transfer-linked. Legs whose
        partner never appears import unlinked so balances stay correct.
        """
        rows: list[dict] = []
        # Pairing pool: (account_a, account_b, date, abs_amount) → unmatched
        # legs (either sign) awaiting their opposite-sign partner.
        unpaired_legs: dict[tuple, list[dict]] = {}

        payee_names = {txn.payee for txn in budget.transactions if txn.payee}
        payee_map = await self.payee_repo.find_or_create_batch(self.budget_id, list(payee_names))

        for txn in budget.transactions:
            try:
                account = await self._get_or_create_account(txn.account_name, result)

                category_id: uuid.UUID | None = None
                if txn.category_group and txn.category:
                    cat = await self._get_or_create_category(
                        txn.category_group, txn.category, result
                    )
                    category_id = cat.id

                row = {
                    "id": uuid.uuid4(),
                    "budget_id": self.budget_id,
                    "account_id": account.id,
                    "date": txn.date,
                    "amount": txn.amount,
                    "payee_id": payee_map.get(txn.payee) if txn.payee else None,
                    "category_id": category_id,
                    "memo": txn.memo or None,
                    "cleared": txn.cleared,
                    "approved": True,
                    "is_split": False,
                    "is_deleted": False,
                    "transfer_id": None,
                    "import_id": _generate_import_id(
                        txn.account_name, txn.date, txn.amount, txn.payee or ""
                    ),
                }
                rows.append(row)

                is_transfer_leg = txn.payee.startswith(_TRANSFER_PREFIX) and category_id is None
                if is_transfer_leg:
                    target_name = txn.payee[len(_TRANSFER_PREFIX) :]
                    pair_key = (
                        *sorted((txn.account_name.lower(), target_name.lower())),
                        txn.date,
                        abs(txn.amount),
                    )
                    waiting = unpaired_legs.setdefault(pair_key, [])
                    partner = next((r for r in waiting if r["amount"] == -txn.amount), None)
                    if partner is not None:
                        waiting.remove(partner)
                        row["transfer_id"] = partner["id"]
                        partner["transfer_id"] = row["id"]
                    else:
                        waiting.append(row)

            except Exception as e:
                result.errors.append(f"Transaction {txn.date} {txn.payee}: {e}")
                result.transactions_skipped += 1

        # Make import_ids unique within the batch: two transactions with identical
        # (account, date, amount, payee) produce the same hash, so append ":N" for N>0.
        seen_keys: dict[tuple[uuid.UUID, str], int] = {}
        for row in rows:
            key = (row["account_id"], row["import_id"])
            count = seen_keys.get(key, 0)
            if count > 0:
                row["import_id"] = f"{row['import_id']}:{count}"
            seen_keys[key] = count + 1

        # Deduplicate against existing import_ids before inserting. If one leg
        # of a linked pair already exists, drop the link on the fresh leg
        # rather than pointing at a row that won't be inserted.
        all_import_ids = [r["import_id"] for r in rows if r.get("import_id")]
        existing_ids = await self.transaction_repo.get_existing_import_ids(
            self.budget_id, all_import_ids
        )
        new_rows = [r for r in rows if r.get("import_id") not in existing_ids]
        result.transactions_skipped += len(rows) - len(new_rows)

        new_ids = {r["id"] for r in new_rows}
        for row in new_rows:
            if row["transfer_id"] is not None and row["transfer_id"] not in new_ids:
                row["transfer_id"] = None

        inserted = await self.transaction_repo.bulk_create(new_rows)
        result.transactions_imported += inserted

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
