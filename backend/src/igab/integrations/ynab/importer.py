import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Category, CategoryGroup
from igab.domain.import_identity import disambiguate_in_batch, generate_import_id
from igab.domain.tag_hints import suggest_system_tag
from igab.domain.transfers import linking_breaks_category_rule
from igab.integrations.ynab.models import YNABBudget
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.account_type_service import apply_type, resolve_type
from igab.services.liability_service import ensure_for_account
from igab.services.transaction_service import TransactionService

_TRANSFER_PREFIX = "Transfer : "
_YNAB_INFLOW_GROUP = "Inflow"
_YNAB_INFLOW_CATEGORY = "Ready to Assign"
_YNAB_HIDDEN_GROUP = "Hidden Categories"
_YNAB_CREDIT_CARD_PAYMENTS_GROUP = "Credit Card Payments"
_MAX_ERRORS = 50


_SYSTEM_INCOME_GROUP = "Income"
#: What YNAB's inflow category is called here. YNAB names it after the
#: budget-wide figure it feeds ("Ready to Assign"); in IGAB that figure is the
#: hero, and a category row of the same name sat directly under it showing a
#: number that was neither.
_INFLOW_CATEGORY = "Inflow"


def map_ynab_names(group: str, category: str) -> tuple[str, str]:
    """YNAB's (group, category) → IGAB's. The one mapping, used by the
    importer and by the parity check that reads YNAB's own figures back."""
    if group == _YNAB_INFLOW_GROUP:
        return _SYSTEM_INCOME_GROUP, (
            _INFLOW_CATEGORY if category == _YNAB_INFLOW_CATEGORY else category
        )
    return group, category


def is_credit_card_payments_group(group: str) -> bool:
    """YNAB's own group of card-payment reserves.

    Its categories exist only in the plan (never in the register) and hold
    the cash YNAB sets aside to pay each card. IGAB has no such reserve: a
    card is an on-budget account whose balance already nets against cash in
    Ready to Assign, so importing these assignments reserved the same debt
    twice and lowered Ready to Assign by every dollar ever assigned there.
    """
    return group == _YNAB_CREDIT_CARD_PAYMENTS_GROUP


@dataclass
class TaggedCategory:
    """One tag the import applied, and why."""

    category_id: uuid.UUID
    system_key: str
    #: The name that triggered the hint -- the category's own or its group's.
    #: Shown in the review so a person can check the guess rather than take it
    #: on faith.
    matched_on: str


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
    #: Transfer legs that are one line of a split. Never paired, by design:
    #: money fields live on a split's parent, so linking a child would put the
    #: pair's two halves at different levels. Counted into the unpaired total
    #: so the number the user is shown is the number of rows they can act on —
    #: they are repairable by hand from the register like any orphan leg.
    transfer_legs_in_splits: int = 0
    #: Categories the import tagged from their names (Savings, Long-term
    #: expense). Reported because a tag changes how that category's spending
    #: is classified in reports — applying it silently would be a number
    #: moving for a reason the user never saw.
    categories_tagged: int = 0
    #: Which categories, and what key each was given. The count alone cannot
    #: answer the question the review exists for -- "show me what you did" --
    #: and it cannot be recovered later either, because nothing on the join
    #: table records whether a tag was guessed or chosen.
    tagged_categories: list["TaggedCategory"] = field(default_factory=list)
    #: Plan rows in YNAB's Credit Card Payments group, left out on purpose —
    #: see `is_credit_card_payments_group`. Reported with the money they would
    #: have taken out of Ready to Assign, so the user can see why the figure
    #: differs from YNAB's by exactly that.
    credit_card_payment_assignments_skipped: int = 0
    credit_card_payment_reserves_skipped: Decimal = Decimal("0")
    #: How the imported budget compares with the export's own figures — set
    #: by the import route after the import, None if the check could not run.
    parity: Any = None
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
        self.tag_repo = TagRepository(session)
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
        # Before any category exists, so the name-based tagging below has real
        # tags to point at. A budget created by import otherwise reaches the
        # tags endpoint (which backfills) only if the user opens Settings.
        await seed_system_tags(self.session, self.budget_id)
        # Rows the parser had to drop because their amount was unreadable.
        # Carried through rather than swallowed: the import summary is the
        # only place a user would ever learn a row did not make it.
        result.errors.extend(budget.errors[:_MAX_ERRORS])
        await self._seed_arrangement(budget, result)
        await self._import_transactions(budget, result)
        await self._import_assignments(budget, result)
        return result

    async def _seed_arrangement(self, budget: YNABBudget, result: ImportResult) -> None:
        """Create the groups and categories in YNAB's own order, before any
        row needs them.

        Plan.csv lists every category in every month in the arrangement the
        user sees in YNAB — not alphabetically — so the export's final month
        is the layout to keep. Without this every imported group and category
        landed at position 0 and the grid showed them in whatever order
        Postgres returned that day. Categories that appear only in the
        register are created later and go last in their group.
        """
        if not budget.plan_rows:
            return
        last = max(row.month for row in budget.plan_rows)
        group_positions: dict[str, int] = {}
        next_in_group: dict[str, int] = {}
        for row in budget.plan_rows:
            if row.month != last or is_credit_card_payments_group(row.category_group):
                continue
            if row.category_group not in group_positions:
                group_positions[row.category_group] = len(group_positions)
            position = next_in_group.get(row.category_group, 0)
            next_in_group[row.category_group] = position + 1
            await self._get_or_create_category(
                row.category_group,
                row.category,
                result,
                group_sort_order=group_positions[row.category_group],
                sort_order=position,
            )

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

    def _may_link(self, a: dict, b: dict) -> bool:
        """May these two legs be linked as one transfer?

        The rule itself — a category may only sit on the on-budget side of an
        on↔off pair — lives once, in `domain/transfers.py`, shared with
        transfer create, the edit planner, and the repair pass. A pair that
        fails it stays unpaired and visible rather than linked wrong.
        """
        on_budget = {acc.id: acc.on_budget for acc in self._account_cache.values()}
        a_on, b_on = on_budget.get(a["account_id"]), on_budget.get(b["account_id"])
        if a_on is None or b_on is None:
            return False
        return not linking_breaks_category_rule(
            a["category_id"] is not None, a_on, b["category_id"] is not None, b_on
        )

    async def _get_or_create_category(
        self,
        group_name: str,
        category_name: str,
        result: ImportResult,
        *,
        group_sort_order: int | None = None,
        sort_order: int | None = None,
    ) -> Category:
        """The category, created on first sight.

        Positions come from `_seed_arrangement`; left None, the repository
        appends the row after the last one in its budget or group.
        """
        group_name, category_name = map_ynab_names(group_name, category_name)

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
                    sort_order=group_sort_order,
                    is_system=(group_name == _SYSTEM_INCOME_GROUP),
                    # Hidden in YNAB stays hidden here: the history still
                    # imports, the rows just do not clutter the grid.
                    is_hidden=(group_name == _YNAB_HIDDEN_GROUP),
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
                    sort_order=sort_order,
                )
                result.categories_imported += 1
                await self._suggest_tag(category, group.name, result)
            self._category_cache[cache_key] = category

        return self._category_cache[cache_key]

    async def _suggest_tag(self, category: Category, group_name: str, result: ImportResult) -> None:
        """Tag a freshly created category when its name plainly says what it is.

        Without this a YNAB import produces a savings report that is empty
        forever: nothing else tags categories, and the only place to do it by
        hand is a section of the category inspector the user has no reason to
        open. Counted in the summary, because a tag that changes how money is
        classified must not be applied silently.

        New categories only — an existing category's tags are the user's.

        Records which category got which key, not just how many: the import
        review opens on exactly these rows, and no other source can say which
        of a category's tags the app guessed.
        """
        suggestion = suggest_system_tag(category.name, group_name)
        if suggestion is None:
            return
        tag = await self.tag_repo.get_system_tag(self.budget_id, suggestion.system_key)
        if tag is None:
            return
        await self.tag_repo.set_category_tags(category.id, [tag.id])
        result.categories_tagged += 1
        result.tagged_categories.append(
            TaggedCategory(
                category_id=category.id,
                system_key=suggestion.system_key,
                matched_on=suggestion.matched_on,
            )
        )

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
        leg carrying a category (YNAB's off-budget spending transfer) links to
        its far side like any other, keeping its category — so the mortgage
        payment still counts as spending AND names the account it went to. It
        links only where the category is legal on that pair (`_may_link`):
        the on-budget side of an on↔off transfer. Legs whose partner never
        appears import unlinked so balances stay correct.

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
                        "created_via": "import",
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
                        if (
                            leg.category_group
                            and leg.category
                            and not is_credit_card_payments_group(leg.category_group)
                        ):
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
                                "created_via": "import",
                                "is_deleted": False,
                                "transfer_id": None,
                                "parent_transaction_id": parent_row["id"],
                                # assigned once parent import_ids are final
                                "import_id": None,
                            }
                        )
                    # A transfer that is one line of a split never enters the
                    # pairing pool (see transfer_legs_in_splits) — but it is
                    # still an unlinked transfer leg, so count it rather than
                    # let it look like ordinary spending.
                    if txn.payee.startswith(_TRANSFER_PREFIX):
                        # Counted the way UNPAIRED_TRANSFER_LEG counts: the
                        # parent (never categorized) plus every uncategorized
                        # child, since children inherit the transfer payee.
                        result.transfer_legs_in_splits += 1 + sum(
                            1 for kid in children if kid["category_id"] is None
                        )

                    # Append only after every leg resolved, so a failed leg
                    # can never leave a parent whose children don't sum to it.
                    rows.append(parent_row)
                    split_children[parent_row["id"]] = children
                    continue

                category_id: uuid.UUID | None = None
                if (
                    txn.category_group
                    and txn.category
                    and not is_credit_card_payments_group(txn.category_group)
                ):
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
                    "created_via": "import",
                    "is_deleted": False,
                    "transfer_id": None,
                    "parent_transaction_id": None,
                    "import_id": generate_import_id(
                        account.id, txn.date, txn.amount, txn.payee or ""
                    ),
                }
                rows.append(row)

                # A categorized leg is a YNAB *spending transfer* (a mortgage
                # payment out of checking) and pairs like any other. Excluding
                # it left 169 rows unlinked on one real export — every one of
                # them a transfer whose far side the user could see in the
                # other account but never reach from this one.
                if txn.payee.startswith(_TRANSFER_PREFIX):
                    target_name = txn.payee[len(_TRANSFER_PREFIX) :]
                    pair_key = (
                        *sorted((txn.account_name.lower(), target_name.lower())),
                        txn.date,
                        abs(txn.amount),
                    )
                    waiting = unpaired_legs.setdefault(pair_key, [])
                    partner = next(
                        (
                            r
                            for r in waiting
                            if r["amount"] == -txn.amount and self._may_link(r, row)
                        ),
                        None,
                    )
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
        # Must equal what UNPAIRED_TRANSFER_LEG selects, or the hygiene panel
        # promises a number the list it links to cannot show. That predicate is
        # transfer-payee + no link + NO CATEGORY, so:
        #   - categorized legs are excluded even when they end up unpaired. A
        #     categorized leg is a spending transfer: already counted as
        #     spending, so nothing is misreported by its missing partner.
        #     (They still take part in pairing above — being unproblematic is
        #     not a reason to leave a link unmade.)
        #   - split rows ARE included: they carry the transfer payee and never
        #     enter the pairing pool, so the predicate lists them.
        result.transfer_legs_unpaired = (
            sum(1 for legs in unpaired_legs.values() for leg in legs if leg["category_id"] is None)
            + result.transfer_legs_in_splits
        )

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
            if is_credit_card_payments_group(entry.category_group):
                result.credit_card_payment_assignments_skipped += 1
                result.credit_card_payment_reserves_skipped += entry.assigned
                continue
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
