import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Category, CategoryGroup
from igab.domain.import_identity import disambiguate_in_batch, generate_import_id
from igab.integrations.ynab.models import YNABBudget
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.account_type_service import apply_type, resolve_type
from igab.services.liability_service import ensure_for_account
from igab.services.transaction_service import TransactionService

_TRANSFER_PREFIX = "Transfer : "
_YNAB_INFLOW_GROUP = "Inflow"
_MAX_ERRORS = 50


_SYSTEM_INCOME_GROUP = "Income"


@dataclass
class ImportResult:
    accounts_imported: int = 0
    category_groups_imported: int = 0
    categories_imported: int = 0
    transactions_imported: int = 0
    transactions_skipped: int = 0
    assignments_imported: int = 0
    # User-chosen exclusions (closed/archived YNAB accounts) — separate from
    # transactions_skipped, which means dedup hits and row errors.
    accounts_skipped: int = 0
    #: Imported in full, then closed at the user's request. Reported back so
    #: the confirmation reflects the choice — 14 accounts quietly vanishing
    #: from the pickers with no mention of it reads like a bug.
    accounts_closed: int = 0
    transactions_excluded: int = 0
    #: Transfer legs whose partner leg never turned up, so they import
    #: unlinked. Balances stay right either way, but a non-zero count means the
    #: export was not what we expected — the partner account was skipped, or
    #: the legs did not match on (accounts, date, amount). Surfaced rather than
    #: swallowed: silently unlinked legs are indistinguishable from real
    #: income and expense until someone reads a report and disbelieves it.
    transfer_legs_unpaired: int = 0
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
        skip_accounts: set[str] | None = None,
        close_accounts: set[str] | None = None,
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
        # Accounts to leave out entirely (matched case-insensitively, like
        # _get_or_create_account). YNAB exports include archived accounts with
        # no marker, so exclusion is a per-account user decision.
        self.skip_accounts = {name.lower() for name in (skip_accounts or set())}
        # Accounts to import in full and then close. Unlike skip_accounts this
        # changes nothing about what is created: every transaction arrives and
        # counts toward net worth, history and reports, and transfers still
        # pair up. The account is simply hidden from pickers and report
        # filters, which is what a 2019-dormant account wants.
        self.close_accounts = {name.lower() for name in (close_accounts or set())}
        # name → Account
        self._account_cache: dict[str, Account] = {}
        # group name → CategoryGroup
        self._group_cache: dict[str, CategoryGroup] = {}
        # (group_id, category name lower) → Category
        self._category_cache: dict[tuple[uuid.UUID, str], Category] = {}

    async def import_budget(self, budget: YNABBudget) -> ImportResult:
        result = ImportResult()
        # Rows the parser had to drop because their amount was unreadable.
        # Carried through rather than swallowed: the import summary is the
        # only place a user would ever learn a row did not make it.
        result.errors.extend(budget.errors[:_MAX_ERRORS])
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
            # Through the shared derivation so account_type_id/classification
            # are always set — imported accounts must not fall out of the
            # sidebar or net worth for lack of a classification.
            type_row = await resolve_type(self.session, self.budget_id, account_type)
            account = await self.account_repo.create(
                budget_id=self.budget_id,
                name=name,
                is_closed=name.lower() in self.close_accounts,
                **apply_type(type_row, on_budget),
            )
            # Importing a budget with a mortgage is the scenario the loan
            # features were built for, and it was the one that never reached
            # them: the importer creates accounts and never a liability.
            await ensure_for_account(self.session, account)
            result.accounts_imported += 1
            if account.is_closed:
                result.accounts_closed += 1

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

    async def _resolve_payees(
        self, budget: YNABBudget, payee_names: set[str], result: ImportResult
    ) -> dict[str, uuid.UUID]:
        """Resolve every payee name, turning "Transfer : <account>" into a real
        transfer payee rather than a plain payee that merely looks like one.

        `Payee.transfer_account_id` is what keeps a leg out of income/expense
        once its partner link is missing, and what keeps transfer payees out of
        payee pickers and AI suggestions. A YNAB register names the partner
        account in the payee column, so the mapping is available here — it was
        simply never used, and every imported transfer payee came out as an
        ordinary payee named "Transfer : Vanguard".

        Accounts are created up front (they were previously created lazily per
        row) because a transfer payee needs its target account's id to exist.
        """
        # Every account that will actually import, in first-seen order.
        account_names: list[str] = []
        seen: set[str] = set()
        for txn in budget.transactions:
            lowered = txn.account_name.lower()
            if lowered in self.skip_accounts or lowered in seen:
                continue
            seen.add(lowered)
            account_names.append(txn.account_name)
        for name in account_names:
            await self._get_or_create_account(name, result)

        by_lower = {name.lower(): name for name in account_names}

        payee_map: dict[str, uuid.UUID] = {}
        plain_names: list[str] = []
        for name in payee_names:
            if not name.startswith(_TRANSFER_PREFIX):
                plain_names.append(name)
                continue
            target = name[len(_TRANSFER_PREFIX) :]
            actual = by_lower.get(target.lower())
            if actual is None:
                # Names an account the user chose to skip (or one that never
                # appears in the register). There is no account to point at, so
                # it stays an ordinary payee — counted below so the user sees
                # that these rows are not recognised as transfers.
                plain_names.append(name)
                continue
            account = self._account_cache[actual]
            payee = await self.payee_repo.find_or_create_transfer(
                self.budget_id, account.id, account.name
            )
            payee_map[name] = payee.id

        payee_map.update(await self.payee_repo.find_or_create_batch(self.budget_id, plain_names))
        return payee_map

    async def _import_transactions(self, budget: YNABBudget, result: ImportResult) -> None:
        """Import every register row — transfers included — as bulk rows with
        deterministic import_ids (fully idempotent re-import), then link
        transfer legs mutually via ids generated client-side.

        Per-leg cleared/reconciled state from YNAB is preserved. A transfer
        leg carrying a category (YNAB's off-budget spending transfer) imports
        as a plain categorized row and is NOT transfer-linked. Legs whose
        partner never appears import unlinked so balances stay correct.

        Transactions the parser reassembled from YNAB's flattened split legs
        become a parent row (is_split, no category, amount = bank total — the
        row sync matching and account balances see) plus child rows carrying
        the per-leg category/amount/memo. Children ride with their parent:
        import_ids derive from the parent's, and a skipped parent skips its
        children. Counters count top-level transactions only, matching YNAB's
        register view.
        """
        rows: list[dict] = []
        # parent row id → its child rows (split legs)
        split_children: dict[uuid.UUID, list[dict]] = {}
        # Pairing pool: (account_a, account_b, date, abs_amount) → unmatched
        # legs (either sign) awaiting their opposite-sign partner.
        unpaired_legs: dict[tuple, list[dict]] = {}

        # Payees only from rows that will import — otherwise every payee that
        # appears solely in a skipped account becomes an orphan payee row.
        payee_names = {
            txn.payee
            for txn in budget.transactions
            if txn.payee and txn.account_name.lower() not in self.skip_accounts
        }
        payee_map = await self._resolve_payees(budget, payee_names, result)

        skipped_account_names: set[str] = set()
        for txn in budget.transactions:
            try:
                if txn.account_name.lower() in self.skip_accounts:
                    # Neither the account nor any of its rows is created. A
                    # kept account's transfer leg pointing here simply never
                    # finds a partner and imports unlinked — the existing
                    # missing-partner path — so kept balances stay correct.
                    skipped_account_names.add(txn.account_name.lower())
                    result.transactions_excluded += 1
                    continue

                account = await self._get_or_create_account(txn.account_name, result)

                if txn.splits:
                    parent_row = {
                        "id": uuid.uuid4(),
                        "budget_id": self.budget_id,
                        "account_id": account.id,
                        "date": txn.date,
                        "amount": txn.amount,
                        "payee_id": payee_map.get(txn.payee) if txn.payee else None,
                        "category_id": None,
                        "memo": txn.memo or None,
                        "cleared": txn.cleared,
                        "approved": True,
                        "is_split": True,
                        "is_deleted": False,
                        "transfer_id": None,
                        "parent_transaction_id": None,
                        "import_id": generate_import_id(
                            account.id, txn.date, txn.amount, txn.payee or ""
                        ),
                    }
                    children: list[dict] = []
                    for leg in txn.splits:
                        leg_category_id: uuid.UUID | None = None
                        if leg.category_group and leg.category:
                            cat = await self._get_or_create_category(
                                leg.category_group, leg.category, result
                            )
                            leg_category_id = cat.id
                        children.append(
                            {
                                "id": uuid.uuid4(),
                                "budget_id": self.budget_id,
                                "account_id": account.id,
                                "date": txn.date,
                                "amount": leg.amount,
                                "payee_id": payee_map.get(txn.payee) if txn.payee else None,
                                "category_id": leg_category_id,
                                "memo": leg.memo,
                                "cleared": txn.cleared,
                                "approved": True,
                                "is_split": False,
                                "is_deleted": False,
                                "transfer_id": None,
                                "parent_transaction_id": parent_row["id"],
                                # assigned once parent import_ids are final
                                "import_id": None,
                            }
                        )
                    # Append only after every leg resolved, so a failed leg
                    # can never leave a parent whose children don't sum to it.
                    rows.append(parent_row)
                    split_children[parent_row["id"]] = children
                    continue

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
                    "parent_transaction_id": None,
                    "import_id": generate_import_id(
                        account.id, txn.date, txn.amount, txn.payee or ""
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
                # One flush failure poisons the session, so every later row
                # raises the same message — cap the list instead of returning
                # thousands of identical entries.
                if len(result.errors) < _MAX_ERRORS:
                    result.errors.append(f"Transaction {txn.date} {txn.payee}: {e}")
                elif len(result.errors) == _MAX_ERRORS:
                    result.errors.append("… more rows failed; see server logs")
                result.transactions_skipped += 1

        result.accounts_skipped = len(skipped_account_names)
        result.transfer_legs_unpaired = sum(len(legs) for legs in unpaired_legs.values())

        disambiguate_in_batch(rows)

        # Split children derive their import_ids from the parent's final
        # (uniquified) one. The ":s" prefix can't collide with the numeric
        # duplicate suffix above.
        for row in rows:
            for pos, kid in enumerate(split_children.get(row["id"], ()), start=1):
                kid["import_id"] = f"{row['import_id']}:s{pos}"

        # Deduplicate against existing import_ids before inserting. If one leg
        # of a linked pair already exists, drop the link on the fresh leg
        # rather than pointing at a row that won't be inserted.
        all_children = [kid for kids in split_children.values() for kid in kids]
        all_import_ids = [r["import_id"] for r in [*rows, *all_children] if r.get("import_id")]
        existing_ids = await self.transaction_repo.get_existing_import_ids(
            self.budget_id, all_import_ids
        )
        new_rows = [r for r in rows if r.get("import_id") not in existing_ids]
        result.transactions_skipped += len(rows) - len(new_rows)

        new_ids = {r["id"] for r in new_rows}
        # Links are applied AFTER insert (bulk_link_transfers), never in the
        # insert rows themselves: bulk_create chunks into one statement per
        # 1000 rows and Postgres checks the transfer_id self-FK at end of
        # statement, so a pair straddling a chunk boundary blew up with
        # "Key (transfer_id)=... is not present in table transactions" on any
        # import over 1000 rows. Partner rows that already exist from a prior
        # import are dropped, as before.
        links: list[tuple[uuid.UUID, uuid.UUID]] = []
        for row in new_rows:
            if row["transfer_id"] is not None and row["transfer_id"] in new_ids:
                links.append((row["id"], row["transfer_id"]))
            row["transfer_id"] = None

        # Children insert only when their parent does (fresh parent uuid —
        # a child can never attach to a row from a previous import).
        new_children = [
            kid
            for parent_id, kids in split_children.items()
            if parent_id in new_ids
            for kid in kids
            if kid["import_id"] not in existing_ids
        ]

        # Parents must hit the table before their children (FK).
        inserted = await self.transaction_repo.bulk_create(new_rows)
        await self.transaction_repo.bulk_create(new_children)
        await self.transaction_repo.bulk_link_transfers(links)
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
