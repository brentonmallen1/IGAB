"""Phase 4 spec: YNAB import is fully idempotent — including transfers —
with per-leg cleared state preserved and both legs linked."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from igab.db.models import Account, Transaction
from igab.integrations.ynab.importer import YNABImporter
from igab.integrations.ynab.models import (
    YNABBudget,
    YNABPlanRow,
    YNABSplitLeg,
    YNABTransaction,
)
from igab.repositories.category_repo import CategoryGroupRepository
from igab.repositories.txn_filters import UNPAIRED_TRANSFER_LEG

from .factories import create_budget, create_user, make_services
from .invariants import assert_financial_invariants

JAN5 = date(2026, 1, 5)


def _importer(
    services, db_session, budget, account_types=None, skip_accounts=None, close_accounts=None
) -> YNABImporter:
    return YNABImporter(
        session=db_session,
        budget_id=budget.id,
        account_repo=services.account_repo,
        category_group_repo=CategoryGroupRepository(db_session),
        category_repo=services.category_repo,
        payee_repo=services.payee_repo,
        transaction_repo=services.transaction_repo,
        transaction_service=services.transactions,
        assignment_repo=services.assignment_repo,
        account_types=account_types,
        skip_accounts=skip_accounts,
        close_accounts=close_accounts,
    )


def _txn(account, payee, amount, *, cleared="cleared", category=None, group=None, memo=None):
    return YNABTransaction(
        account_name=account,
        date=JAN5,
        payee=payee,
        category_group=group,
        category=category,
        memo=memo,
        amount=Decimal(amount),
        cleared=cleared,
    )


def _budget_with_transfer() -> YNABBudget:
    return YNABBudget(
        transactions=[
            _txn("Checking", "Employer", "2000.00", group="Inflow", category="Ready to Assign"),
            _txn("Checking", "Transfer : Savings", "-500.00", cleared="reconciled"),
            _txn("Savings", "Transfer : Checking", "500.00", cleared="cleared"),
            _txn("Checking", "Corner Market", "-60.00", group="Everyday", category="Groceries"),
        ]
    )


async def test_reimport_fully_idempotent_including_transfers(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    first = await _importer(services, db_session, budget).import_budget(_budget_with_transfer())
    assert first.transactions_imported == 4
    assert first.errors == []

    second = await _importer(services, db_session, budget).import_budget(_budget_with_transfer())
    assert second.transactions_imported == 0, (
        f"re-import created duplicates (skipped={second.transactions_skipped}, "
        f"errors={second.errors})"
    )

    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    assert await services.account_repo.get_balance(accounts["Checking"].id) == Decimal("1440.00")
    assert await services.account_repo.get_balance(accounts["Savings"].id) == Decimal("500.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_transfer_legs_linked_with_per_leg_cleared(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    await _importer(services, db_session, budget).import_budget(_budget_with_transfer())

    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    checking_txns = await services.transaction_repo.get_for_account(accounts["Checking"].id)
    savings_txns = await services.transaction_repo.get_for_account(accounts["Savings"].id)

    out_leg = next(t for t in checking_txns if t.amount == Decimal("-500.00"))
    in_leg = next(t for t in savings_txns if t.amount == Decimal("500.00"))

    assert out_leg.transfer_id == in_leg.id
    assert in_leg.transfer_id == out_leg.id
    assert out_leg.cleared == "reconciled", "per-leg cleared state from YNAB preserved"
    assert in_leg.cleared == "cleared"
    await assert_financial_invariants(db_session, budget.id)


async def test_unpaired_transfer_leg_imports_as_plain_row(db_session):
    """A transfer whose partner account never appears (e.g. deleted in YNAB)
    still imports — as an unlinked row — so balances stay correct."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    data = YNABBudget(transactions=[_txn("Checking", "Transfer : Old Closed Account", "-75.00")])
    result = await _importer(services, db_session, budget).import_budget(data)

    assert result.transactions_imported == 1
    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    assert await services.account_repo.get_balance(accounts["Checking"].id) == Decimal("-75.00")


async def test_categorized_transfer_leg_imports_categorized_unlinked(db_session):
    """YNAB transfers to off-budget accounts carry a category (they're
    spending). Here BOTH accounts are on-budget (no type override, so
    "Mortgage" imports as an ordinary checking account), and a category on an
    on↔on transfer would count money that never left the budget as spending —
    so the legs stay unlinked. See TestSpendingTransfersPair for the same
    shape with a genuinely off-budget far side, which does link."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    data = YNABBudget(
        transactions=[
            _txn(
                "Checking",
                "Transfer : Mortgage",
                "-1200.00",
                group="Obligations",
                category="Mortgage Payment",
            ),
            _txn("Mortgage", "Transfer : Checking", "1200.00"),
        ]
    )
    result = await _importer(services, db_session, budget).import_budget(data)

    assert result.transactions_imported == 2
    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    checking_txns = await services.transaction_repo.get_for_account(accounts["Checking"].id)
    leg = checking_txns[0]
    assert leg.category_id is not None, "the category is the point — it's spending"
    assert leg.transfer_id is None
    await assert_financial_invariants(db_session, budget.id)


async def test_imported_rows_are_stamped_import(db_session):
    """The bulk insert path bypasses TransactionService.create, so it stamps
    its own origin — flat rows, split parents and split lines alike."""
    from sqlalchemy import select

    from igab.db.models import Transaction

    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    data = YNABBudget(
        transactions=[
            _txn("Checking", "Coffee Shop", "-4.50"),
            _txn("Checking", "Employer", "2000.00", group="Inflow", category="Ready to Assign"),
        ]
    )
    await _importer(services, db_session, budget).import_budget(data)
    rows = (
        (await db_session.execute(select(Transaction).where(Transaction.budget_id == budget.id)))
        .scalars()
        .all()
    )
    assert rows and all(r.created_via == "import" for r in rows)


async def test_same_day_duplicate_rows_both_import(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    data = YNABBudget(
        transactions=[
            _txn("Checking", "Coffee Shop", "-4.50"),
            _txn("Checking", "Coffee Shop", "-4.50"),
        ]
    )
    result = await _importer(services, db_session, budget).import_budget(data)
    assert result.transactions_imported == 2

    again = await _importer(services, db_session, budget).import_budget(data)
    assert again.transactions_imported == 0


async def test_account_type_overrides_applied(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    data = YNABBudget(transactions=[_txn("Brokerage", "Opening", "10000.00")])
    await _importer(
        services,
        db_session,
        budget,
        account_types={"Brokerage": ("investment", False)},
    ).import_budget(data)

    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    brokerage = accounts["Brokerage"]
    assert brokerage.account_type == "investment"
    assert brokerage.on_budget is False


def _split_txn(account, payee, legs, *, cleared="cleared"):
    """legs: (amount, group, category, memo) tuples; total computed."""
    return YNABTransaction(
        account_name=account,
        date=JAN5,
        payee=payee,
        category_group=None,
        category=None,
        memo=None,
        amount=sum((Decimal(a) for a, _, _, _ in legs), Decimal("0")),
        cleared=cleared,
        splits=[
            YNABSplitLeg(category_group=g, category=c, memo=m, amount=Decimal(a))
            for a, g, c, m in legs
        ],
    )


async def _all_rows(db_session, account_id) -> list[Transaction]:
    rows = await db_session.execute(select(Transaction).where(Transaction.account_id == account_id))
    return list(rows.scalars().all())


async def test_split_imports_as_parent_plus_children(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    data = YNABBudget(
        transactions=[
            _split_txn(
                "Checking",
                "BJs Wholesale",
                [
                    ("-63.97", "Everyday", "Groceries", None),
                    ("0.00", "Everyday", "Pets", None),
                    ("-90.93", "Everyday", "Household", "paper towels"),
                ],
                cleared="reconciled",
            )
        ]
    )
    result = await _importer(services, db_session, budget).import_budget(data)

    assert result.errors == []
    assert result.transactions_imported == 1, "a split counts as ONE transaction"

    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    rows = await _all_rows(db_session, accounts["Checking"].id)
    assert len(rows) == 4

    parent = next(r for r in rows if r.is_split)
    assert parent.amount == Decimal("-154.90")
    assert parent.category_id is None
    assert parent.parent_transaction_id is None
    assert parent.cleared == "reconciled"
    assert parent.import_id is not None

    children = sorted(
        (r for r in rows if r.parent_transaction_id == parent.id),
        key=lambda r: r.import_id or "",
    )
    assert [c.amount for c in children] == [
        Decimal("-63.97"),
        Decimal("0.00"),
        Decimal("-90.93"),
    ]
    assert all(c.cleared == "reconciled" and c.approved for c in children)
    assert all(c.category_id is not None for c in children)
    assert children[2].memo == "paper towels"
    assert [c.import_id for c in children] == [
        f"{parent.import_id}:s1",
        f"{parent.import_id}:s2",
        f"{parent.import_id}:s3",
    ]

    # Balances count the parent only — the bank sees one -154.90 charge
    assert await services.account_repo.get_balance(accounts["Checking"].id) == Decimal("-154.90")
    await assert_financial_invariants(db_session, budget.id)


async def test_split_reimport_fully_idempotent(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    data = YNABBudget(
        transactions=[
            _split_txn(
                "Checking",
                "Target",
                [
                    ("-74.44", "Everyday", "Groceries", None),
                    ("-89.50", "Everyday", "Household", None),
                ],
            )
        ]
    )
    first = await _importer(services, db_session, budget).import_budget(data)
    assert first.transactions_imported == 1

    second = await _importer(services, db_session, budget).import_budget(data)
    assert second.transactions_imported == 0, (
        f"re-import duplicated a split (errors={second.errors})"
    )

    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    rows = await _all_rows(db_session, accounts["Checking"].id)
    assert len(rows) == 3, "parent + 2 children, nothing duplicated"
    await assert_financial_invariants(db_session, budget.id)


async def test_split_and_identical_flat_row_coexist(db_session):
    """A split totalling -50.00 and a plain -50.00 row, same day and payee:
    both must import (distinct import_ids) and re-import must stay clean."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    data = YNABBudget(
        transactions=[
            _split_txn(
                "Checking",
                "Corner Market",
                [
                    ("-30.00", "Everyday", "Groceries", None),
                    ("-20.00", "Everyday", "Household", None),
                ],
            ),
            _txn("Checking", "Corner Market", "-50.00", group="Everyday", category="Groceries"),
        ]
    )
    first = await _importer(services, db_session, budget).import_budget(data)
    assert first.transactions_imported == 2
    assert first.errors == []

    second = await _importer(services, db_session, budget).import_budget(data)
    assert second.transactions_imported == 0

    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    rows = await _all_rows(db_session, accounts["Checking"].id)
    assert len(rows) == 4, "split parent + 2 children + flat row"
    assert await services.account_repo.get_balance(accounts["Checking"].id) == Decimal("-100.00")
    await assert_financial_invariants(db_session, budget.id)


class TestSkipAccounts:
    """YNAB exports include archived accounts with no marker — the user
    excludes them per-account, and neither the account nor any of its rows
    (nor payees that only it used) may reach the budget."""

    async def test_skipped_account_and_its_rows_are_not_imported(self, db_session):
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)

        data = YNABBudget(
            transactions=[
                _txn("Checking", "Employer", "2000.00", group="Inflow", category="Ready to Assign"),
                _txn("Old Card", "Ghost Shop", "-40.00", group="Everyday", category="Groceries"),
                _txn("Old Card", "Ghost Shop", "-15.00", group="Everyday", category="Groceries"),
            ]
        )
        result = await _importer(
            services, db_session, budget, skip_accounts={"Old Card"}
        ).import_budget(data)

        assert result.transactions_imported == 1
        assert result.accounts_imported == 1
        assert result.accounts_skipped == 1
        assert result.transactions_excluded == 2
        assert result.transactions_skipped == 0, "exclusions are not error-skips"

        accounts = {a.name for a in await services.account_repo.get_all(budget.id)}
        assert accounts == {"Checking"}
        rows = (
            (
                await db_session.execute(
                    select(Transaction).where(Transaction.budget_id == budget.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        # A payee used only by the skipped account must not become an orphan row
        payees = {p.name for p in await services.payee_repo.get_all(budget.id)}
        assert "Ghost Shop" not in payees
        assert "Employer" in payees
        await assert_financial_invariants(db_session, budget.id)

    async def test_transfer_leg_to_skipped_account_imports_unlinked(self, db_session):
        """The kept side of a transfer into a skipped account behaves exactly
        like a transfer whose partner never appears: plain unlinked row, so
        the kept account's balance stays correct."""
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)

        result = await _importer(
            services, db_session, budget, skip_accounts={"Savings"}
        ).import_budget(_budget_with_transfer())

        assert result.accounts_skipped == 1
        assert result.transactions_excluded == 1
        assert result.transactions_imported == 3

        accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
        assert set(accounts) == {"Checking"}
        rows = (
            (
                await db_session.execute(
                    select(Transaction).where(Transaction.budget_id == budget.id)
                )
            )
            .scalars()
            .all()
        )
        leg = next(r for r in rows if r.amount == Decimal("-500.00"))
        assert leg.transfer_id is None
        assert await services.account_repo.get_balance(accounts["Checking"].id) == Decimal(
            "1440.00"
        )
        await assert_financial_invariants(db_session, budget.id)

    async def test_skip_matches_case_insensitively(self, db_session):
        """_get_or_create_account matches names case-insensitively; skipping
        must use the same rule or a case difference resurrects the account."""
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)

        data = YNABBudget(transactions=[_txn("Old Card", "Shop", "-5.00")])
        result = await _importer(
            services, db_session, budget, skip_accounts={"old card"}
        ).import_budget(data)

        assert result.transactions_excluded == 1
        assert await services.account_repo.get_all(budget.id) == []


class TestBulkChunkBoundaries:
    """Imports >1000 rows split into multiple INSERT statements. Postgres
    checks the transfer_id self-FK at end of statement, so a linked pair
    straddling a chunk boundary used to fail with ForeignKeyViolation —
    the first real-world multi-account export to exceed 1000 rows died with
    "Key (transfer_id)=... is not present in table transactions"."""

    def _big_budget_with_boundary_transfer(self, chunk: int) -> YNABBudget:
        # Filler up to one row before the boundary, then the transfer pair's
        # legs land at positions chunk-1 and chunk+1 — different statements.
        txns = [
            _txn("Checking", f"Shop {i}", "-1.00", group="Everyday", category="Groceries")
            for i in range(chunk - 1)
        ]
        txns.append(_txn("Checking", "Transfer : Savings", "-500.00"))
        txns.append(_txn("Checking", "Shop x", "-2.00", group="Everyday", category="Groceries"))
        txns.append(_txn("Savings", "Transfer : Checking", "500.00"))
        return YNABBudget(transactions=txns)

    async def test_transfer_pair_straddling_a_chunk_boundary_links(self, db_session):
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)

        chunk = services.transaction_repo._BULK_CHUNK
        data = self._big_budget_with_boundary_transfer(chunk)
        result = await _importer(services, db_session, budget).import_budget(data)

        assert result.errors == []
        assert result.transactions_imported == len(data.transactions)

        rows = (
            (
                await db_session.execute(
                    select(Transaction).where(
                        Transaction.budget_id == budget.id,
                        Transaction.amount.in_([Decimal("-500.00"), Decimal("500.00")]),
                    )
                )
            )
            .scalars()
            .all()
        )
        out_leg = next(r for r in rows if r.amount == Decimal("-500.00"))
        in_leg = next(r for r in rows if r.amount == Decimal("500.00"))
        assert out_leg.transfer_id == in_leg.id
        assert in_leg.transfer_id == out_leg.id
        await assert_financial_invariants(db_session, budget.id)

    async def test_reimport_of_boundary_straddling_export_is_idempotent(self, db_session):
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)

        chunk = services.transaction_repo._BULK_CHUNK
        data = self._big_budget_with_boundary_transfer(chunk)
        await _importer(services, db_session, budget).import_budget(data)
        again = await _importer(services, db_session, budget).import_budget(data)

        assert again.transactions_imported == 0
        assert again.transactions_skipped == len(data.transactions)
        count = (
            (
                await db_session.execute(
                    select(Transaction).where(Transaction.budget_id == budget.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(count) == len(data.transactions)
        await assert_financial_invariants(db_session, budget.id)


class TestImportAndClose:
    """Closing beats skipping for a dormant account, and the difference is the
    whole point: `skip` never creates the account, so its history does not
    exist and transfers to it have nothing to pair with. `close` imports
    everything and hides the account from pickers and report filters.

    A real export carried 14 accounts with no activity since 2019–2021. Told
    to skip them, a user loses the history that makes past months add up.
    """

    async def _budget(self, db_session):
        user = await create_user(db_session)
        return make_services(db_session), await create_budget(db_session, user)

    async def test_a_closed_account_still_imports_every_transaction(self, db_session):
        services, budget = await self._budget(db_session)
        importer = _importer(services, db_session, budget, close_accounts={"Old Savings"})

        result = await importer.import_budget(
            YNABBudget(
                transactions=[
                    _txn("Old Savings", "Interest", "5.00", category="Income", group="Inflow"),
                    _txn("Old Savings", "Interest", "6.00", category="Income", group="Inflow"),
                ],
                budget_entries=[],
            )
        )
        await db_session.flush()

        # Reported back, not silent: 14 accounts vanishing from the pickers
        # with no mention of it in the confirmation reads like a bug.
        assert result.accounts_closed == 1
        assert result.accounts_skipped == 0, "closing is not skipping"
        assert result.transactions_imported == 2

        account = (
            await db_session.execute(
                select(Account).where(Account.budget_id == budget.id, Account.name == "Old Savings")
            )
        ).scalar_one()
        assert account.is_closed is True
        assert await services.transaction_repo.count_for_account(account.id) == 2
        assert await services.account_repo.get_balance(account.id) == Decimal("11.00")
        await assert_financial_invariants(db_session, budget.id)

    async def test_matching_is_case_insensitive_like_every_other_name_match(self, db_session):
        services, budget = await self._budget(db_session)
        importer = _importer(services, db_session, budget, close_accounts={"OLD SAVINGS"})

        await importer.import_budget(
            YNABBudget(transactions=[_txn("Old Savings", "Interest", "5.00")], budget_entries=[])
        )
        await db_session.flush()

        account = (
            await db_session.execute(
                select(Account).where(Account.budget_id == budget.id, Account.name == "Old Savings")
            )
        ).scalar_one()
        assert account.is_closed is True

    async def test_an_account_not_named_arrives_open(self, db_session):
        services, budget = await self._budget(db_session)
        importer = _importer(services, db_session, budget, close_accounts={"Old Savings"})

        await importer.import_budget(
            YNABBudget(transactions=[_txn("Checking", "Shop", "-5.00")], budget_entries=[])
        )
        await db_session.flush()

        account = (
            await db_session.execute(
                select(Account).where(Account.budget_id == budget.id, Account.name == "Checking")
            )
        ).scalar_one()
        assert account.is_closed is False

    async def test_a_transfer_to_a_closed_account_still_pairs(self, db_session):
        """The reason close exists. Skipping the far side is what leaves a leg
        unlinked and reading as real income or spending in reports."""
        services, budget = await self._budget(db_session)
        importer = _importer(services, db_session, budget, close_accounts={"Old Savings"})

        await importer.import_budget(
            YNABBudget(
                transactions=[
                    _txn("Checking", "Transfer : Old Savings", "-100.00"),
                    _txn("Old Savings", "Transfer : Checking", "100.00"),
                ],
                budget_entries=[],
            )
        )
        await db_session.flush()

        legs = (
            (
                await db_session.execute(
                    select(Transaction).where(
                        Transaction.budget_id == budget.id, Transaction.transfer_id.isnot(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(legs) == 2, "both legs linked despite one side being closed"
        await assert_financial_invariants(db_session, budget.id)


async def test_a_parse_error_reaches_the_import_summary(db_session):
    """The parser drops a row it cannot read; the user has to be told.

    Before this, an unreadable amount became Decimal("0") and the transaction
    imported anyway with no money in it — the row count reconciled and only
    the balance was wrong. `result.errors` is the only place a user would ever
    learn a row did not make it.
    """
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    importer = _importer(services, db_session, budget)

    ynab = YNABBudget(
        transactions=[_txn("Checking", "Shop", "-12.00")],
        budget_entries=[],
        errors=["Checking 04/15/2026: cannot parse amount 'N/A'"],
    )
    result = await importer.import_budget(ynab)

    assert result.transactions_imported == 1
    assert any("cannot parse amount" in e for e in result.errors)


class TestTheUnpairedCountAgreesWithTheImporter:
    """`UNPAIRED_TRANSFER_LEG` and `result.transfer_legs_unpaired` answer the
    same question and must return the same number.

    The hygiene panel reports the count and links to the rows. A panel that
    promises 1,286 and opens a list of 1,117 is worse than no panel — that
    exact disagreement is what made the needs-a-category badge untrustworthy.

    The subtle half is the categorized leg: YNAB writes "Transfer : Savings"
    with a category for a spending transfer, and the importer deliberately
    never pairs those. Measured on the real 47-account export, counting them
    made the predicate disagree with the importer by 169 rows. With the
    category condition the two land on 1,117 exactly.
    """

    async def _import(self, db_session, transactions):
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        importer = _importer(services, db_session, budget)
        result = await importer.import_budget(
            YNABBudget(transactions=transactions, budget_entries=[])
        )
        await db_session.flush()
        return services, budget, result

    async def _predicate_count(self, db_session, budget) -> int:
        return (
            await db_session.execute(
                select(func.count())
                .select_from(Transaction)
                .where(
                    Transaction.budget_id == budget.id,
                    Transaction.is_deleted == False,  # noqa: E712
                    UNPAIRED_TRANSFER_LEG,
                )
            )
        ).scalar_one()

    async def test_they_agree_on_a_leg_whose_partner_never_arrived(self, db_session):
        """Both accounts exist; the legs simply never matched on date and
        amount. This is what a real export produces in bulk — 1,117 of them."""
        _, budget, result = await self._import(
            db_session,
            [
                _txn("Savings", "Interest", "1.00", category="Income", group="Inflow"),
                _txn("Checking", "Transfer : Savings", "-500.00"),
                _txn("Checking", "Corner Shop", "-12.00", category="Groceries", group="Everyday"),
            ],
        )

        assert result.transfer_legs_unpaired == 1
        assert await self._predicate_count(db_session, budget) == 1

    async def test_they_agree_that_a_categorized_leg_is_not_a_problem(self, db_session):
        """The 169. A categorized transfer leg is a spending transfer: it is
        meant to be unpaired, and counting it as spending is correct."""
        _, budget, result = await self._import(
            db_session,
            [
                _txn("Brokerage", "Dividend", "2.00", category="Income", group="Inflow"),
                _txn(
                    "Checking",
                    "Transfer : Brokerage",
                    "-500.00",
                    category="Investing",
                    group="Goals",
                ),
            ],
        )

        assert result.transfer_legs_unpaired == 0
        assert await self._predicate_count(db_session, budget) == 0

    async def test_they_agree_when_both_kinds_are_present(self, db_session):
        _, budget, result = await self._import(
            db_session,
            [
                _txn("Savings", "Interest", "1.00", category="Income", group="Inflow"),
                _txn("Brokerage", "Dividend", "2.00", category="Income", group="Inflow"),
                _txn("Checking", "Transfer : Savings", "-500.00"),
                _txn("Checking", "Transfer : Savings", "-25.00"),
                _txn(
                    "Checking",
                    "Transfer : Brokerage",
                    "-90.00",
                    category="Investing",
                    group="Goals",
                ),
            ],
        )

        assert result.transfer_legs_unpaired == 2, "the categorized leg is not a problem"
        assert await self._predicate_count(db_session, budget) == 2

    async def test_they_agree_on_a_properly_paired_transfer(self, db_session):
        _, budget, result = await self._import(
            db_session,
            [
                _txn("Checking", "Transfer : Savings", "-300.00"),
                _txn("Savings", "Transfer : Checking", "300.00"),
            ],
        )

        assert result.transfer_legs_unpaired == 0
        assert await self._predicate_count(db_session, budget) == 0

    async def test_a_leg_naming_an_account_that_never_existed_is_a_different_problem(
        self, db_session
    ):
        """Recorded rather than left to surprise someone.

        When the named account is not in the import at all there is nothing
        for the payee to point at, so the importer leaves it an ordinary payee
        ("it stays an ordinary payee"). Nothing then marks the row as a
        transfer, so it reads as ordinary spending and surfaces through the
        needs-a-category badge instead — which is the right place for it: the
        user has to decide what that money actually was.

        So the two counts differ here by design. The importer matches on the
        payee string and counts it; the predicate needs a resolved transfer
        payee and does not. The real export produced three such rows against
        1,117 of the ordinary kind.
        """
        services, budget, result = await self._import(
            db_session, [_txn("Checking", "Transfer : Nowhere", "-500.00")]
        )

        assert result.transfer_legs_unpaired == 1, "the importer sees the payee string"
        assert await self._predicate_count(db_session, budget) == 0, "no transfer payee exists"

        review = await services.transaction_repo.count_pending_review(budget.id)
        assert review["uncategorized"] == 1, "it surfaces as a row needing a category instead"


class TestSpendingTransfersPair:
    """A categorized transfer leg — YNAB's "spending transfer", a mortgage
    payment made from checking — is still a transfer and still has a far leg
    in the export. The importer used to refuse to even look at it
    (`category_id is None` gated the pairing), so on one real export 169 rows
    imported with their far side visible in the other account and unreachable
    from this one. Pairing them changes no number: the category stays, so the
    spending still counts as spending.
    """

    async def _import(self, db_session, transactions, account_types=None):
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        result = await _importer(
            services, db_session, budget, account_types=account_types
        ).import_budget(YNABBudget(transactions=transactions, budget_entries=[]))
        await db_session.flush()
        return services, budget, result

    async def _rows_by_account(self, db_session, budget):
        rows = (
            await db_session.execute(select(Transaction).where(Transaction.budget_id == budget.id))
        ).scalars()
        out: dict[str, list[Transaction]] = {}
        accounts = {
            a.id: a.name
            for a in (
                await db_session.execute(select(Account).where(Account.budget_id == budget.id))
            ).scalars()
        }
        for row in rows:
            out.setdefault(accounts[row.account_id], []).append(row)
        return out

    async def test_a_categorized_leg_pairs_with_its_tracked_side(self, db_session):
        _, budget, result = await self._import(
            db_session,
            [
                _txn(
                    "Checking",
                    "Transfer : Mortgage",
                    "-2000.00",
                    category="Mortgage",
                    group="Bills",
                ),
                _txn("Mortgage", "Transfer : Checking", "2000.00"),
            ],
            account_types={"Mortgage": ("mortgage", False)},
        )

        by_account = await self._rows_by_account(db_session, budget)
        near = by_account["Checking"][0]
        far = by_account["Mortgage"][0]
        assert near.transfer_id == far.id, "the 169: linked at last"
        assert far.transfer_id == near.id
        assert near.category_id is not None, "and still counted as spending"
        assert result.transfer_legs_unpaired == 0

    async def test_two_categorized_legs_are_left_unlinked(self, db_session):
        """Both sides categorized would count the same money as spending
        twice. Better visibly unpaired than invisibly wrong."""
        _, budget, _ = await self._import(
            db_session,
            [
                _txn("Checking", "Transfer : Savings", "-500.00", category="Fun", group="Everyday"),
                _txn("Savings", "Transfer : Checking", "500.00", category="Fun", group="Everyday"),
            ],
        )
        by_account = await self._rows_by_account(db_session, budget)
        assert by_account["Checking"][0].transfer_id is None
        assert by_account["Savings"][0].transfer_id is None

    async def test_a_categorized_leg_between_on_budget_accounts_is_left_unlinked(self, db_session):
        """On↔on is internal movement; a category on it would count money that
        never left the budget as spending."""
        _, budget, _ = await self._import(
            db_session,
            [
                _txn("Checking", "Transfer : Savings", "-500.00", category="Fun", group="Everyday"),
                _txn("Savings", "Transfer : Checking", "500.00"),
            ],
        )
        by_account = await self._rows_by_account(db_session, budget)
        assert by_account["Checking"][0].transfer_id is None

    async def test_split_transfer_legs_are_counted_not_hidden(self, db_session):
        """A transfer inside a split can't be linked — money fields live on
        the parent — but it must not vanish from the count either, or the
        hygiene panel promises fewer rows than its own list shows."""
        _, budget, result = await self._import(
            db_session,
            [
                # Savings must exist for "Transfer : Savings" to resolve to a
                # real transfer payee — that resolution is what makes a row a
                # transfer leg to every reader, including the predicate.
                _txn("Savings", "Interest", "1.00", category="Income", group="Inflow"),
                _split_txn(
                    "Checking",
                    "Transfer : Savings",
                    [("-300.00", "Everyday", "Groceries", None), ("-200.00", None, None, None)],
                ),
            ],
        )
        # Parent (never categorized) + the one uncategorized child, exactly
        # what UNPAIRED_TRANSFER_LEG selects.
        assert result.transfer_legs_in_splits == 2
        assert result.transfer_legs_unpaired == 2
        predicate_count = (
            await db_session.execute(
                select(func.count())
                .select_from(Transaction)
                .where(
                    Transaction.budget_id == budget.id,
                    Transaction.is_deleted == False,  # noqa: E712
                    UNPAIRED_TRANSFER_LEG,
                )
            )
        ).scalar_one()
        assert predicate_count == result.transfer_legs_unpaired


def _plan_row(month, group, category, assigned="0"):
    return YNABPlanRow(
        month=month,
        category_group=group,
        category=category,
        assigned=Decimal(assigned),
        activity=None,
        available=None,
    )


async def test_the_imported_layout_follows_the_plans_final_month(db_session):
    """Plan.csv lists the categories in the order the user arranged them in
    YNAB. The final month is the current layout; every group and category
    takes its position from it, and a category only the register knows about
    goes last in its group."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    mar, apr = date(2026, 3, 1), date(2026, 4, 1)
    plan = [
        # An older month, in an older arrangement — ignored.
        _plan_row(mar, "Bills", "Rent", "1200"),
        _plan_row(mar, "Wants", "Games"),
        # The final month: Wants before Bills, Water before Rent — neither alphabetical.
        _plan_row(apr, "Wants", "Games", "50"),
        _plan_row(apr, "Wants", "Dining"),
        _plan_row(apr, "Bills", "Water"),
        _plan_row(apr, "Bills", "Rent", "1200"),
        _plan_row(apr, "Bills", "Power"),
    ]
    budget_data = YNABBudget(
        transactions=[
            _txn("Checking", "Employer", "2000.00", group="Inflow", category="Ready to Assign"),
            _txn("Checking", "Landlord", "-1200.00", group="Bills", category="Rent"),
            # Register-only: never in the plan.
            _txn("Checking", "ISP", "-60.00", group="Bills", category="Internet"),
        ],
        budget_entries=[e for e in plan if e.assigned != 0],
        plan_rows=plan,
    )
    await _importer(services, db_session, budget).import_budget(budget_data)

    groups = await CategoryGroupRepository(db_session).get_all(budget.id, include_archived=True)
    assert [g.name for g in groups] == ["Wants", "Bills", "Income"]
    by_name = {g.name: g for g in groups}
    bills = await services.category_repo.get_by_group(by_name["Bills"].id)
    assert [c.name for c in bills] == ["Water", "Rent", "Power", "Internet"]
    assert [c.sort_order for c in bills] == [0, 1, 2, 3]
    wants = await services.category_repo.get_by_group(by_name["Wants"].id)
    assert [c.name for c in wants] == ["Games", "Dining"]


async def test_the_inflow_category_is_named_inflow_not_ready_to_assign(db_session):
    """YNAB names its inflow category after the budget-wide figure it feeds.
    In IGAB that figure is the hero, and a row of the same name sat directly
    under it showing a number that was neither."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await _importer(services, db_session, budget).import_budget(_budget_with_transfer())

    groups = {g.name: g for g in await CategoryGroupRepository(db_session).get_all(budget.id)}
    assert groups["Income"].is_system
    income = await services.category_repo.get_by_group(groups["Income"].id)
    assert [c.name for c in income] == ["Inflow"]


async def test_hidden_categories_stay_hidden_and_card_payment_reserves_are_skipped(db_session):
    """YNAB's Hidden Categories group imports hidden (the history still
    arrives); its Credit Card Payments group does not import at all — IGAB
    nets a card's balance against cash, so those reserves would count the
    same debt twice — and the summary says what was left out and how much."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    # The register helper dates every row JAN5, so the plan is January too.
    jan = date(2026, 1, 1)
    plan = [
        _plan_row(jan, "Everyday", "Groceries", "300"),
        _plan_row(jan, "Hidden Categories", "Old Hobby", "25"),
        _plan_row(jan, "Credit Card Payments", "Visa", "410.50"),
        _plan_row(jan, "Credit Card Payments", "Amex", "89.50"),
    ]
    data = YNABBudget(
        transactions=[
            _txn("Checking", "Employer", "2000.00", group="Inflow", category="Ready to Assign"),
            _txn("Checking", "Corner Market", "-60.00", group="Everyday", category="Groceries"),
            _txn(
                "Checking", "Hobby Shop", "-20.00", group="Hidden Categories", category="Old Hobby"
            ),
        ],
        budget_entries=[e for e in plan if e.assigned != 0],
        plan_rows=plan,
    )
    result = await _importer(services, db_session, budget).import_budget(data)

    everyone = await CategoryGroupRepository(db_session).get_all(budget.id, include_archived=True)
    by_name = {g.name: g for g in everyone}
    assert "Credit Card Payments" not in by_name
    assert by_name["Hidden Categories"].is_archived
    assert not by_name["Everyday"].is_archived
    assert result.credit_card_payment_assignments_skipped == 2
    assert result.credit_card_payment_reserves_skipped == Decimal("500.00")
    assert result.assignments_imported == 2
    # The hidden category's history is there, just out of the grid.
    hidden = await services.category_repo.get_by_group(by_name["Hidden Categories"].id)
    assert [c.name for c in hidden] == ["Old Hobby"]
    # And Ready to Assign is what the register and the kept assignments say:
    # 2000 in, 80 spent, 325 assigned of which 80 was spent → 1920 − 245.
    # With the 500 of card reserves imported it would have read 1175.
    month = await services.budgets.get_budget_summary(budget.id, jan)
    assert month.to_be_assigned == Decimal("1675.00")


async def test_a_tracking_rows_category_is_stripped_and_counted(db_session):
    """A category on a tracking-account row imports as no category.

    Off-budget activity is net-worth movement (domain/transfers.py); the bulk
    insert bypasses the service guard, so the rule is applied at the
    row-build site and the count surfaces in the summary rather than rows
    silently changing shape.
    """
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    data = YNABBudget(
        transactions=[
            _txn("Brokerage", "Vanguard", "-500.00", group="Savings", category="Index Funds"),
            _txn("Checking", "Corner Market", "-60.00", group="Everyday", category="Groceries"),
            _split_txn(
                "Brokerage",
                "Vanguard",
                [
                    ("-300.00", "Savings", "Index Funds", None),
                    ("-200.00", None, None, None),
                ],
            ),
        ]
    )
    result = await _importer(
        services,
        db_session,
        budget,
        account_types={"Brokerage": ("investment", False)},
    ).import_budget(data)

    assert result.tracking_account_categories_stripped == 2
    rows = await services.transaction_repo.get_for_budget(budget.id)
    accounts = {a.id: a for a in await services.account_repo.get_all(budget.id)}
    for row in rows:
        if not accounts[row.account_id].on_budget:
            assert row.category_id is None, "tracking rows must import uncategorized"
    # The on-budget row keeps its category — the rule is about the account.
    checking_rows = [r for r in rows if accounts[r.account_id].on_budget and not r.is_split]
    assert any(r.category_id is not None for r in checking_rows)


async def test_card_payment_reserves_import_onto_the_cards_envelope(db_session):
    """YNAB's Credit Card Payments assignments are the money set aside for
    each card — they land on the card's set-aside envelope (the linked
    category created with the account), and only an entry whose card was
    never imported is counted as skipped."""
    from igab.integrations.ynab.models import YNABBudgetEntry

    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    data = YNABBudget(
        transactions=[
            _txn("Visa", "Corner Market", "-60.00", group="Everyday", category="Groceries")
        ],
        budget_entries=[
            YNABBudgetEntry(
                month=JAN5.replace(day=1),
                category_group="Credit Card Payments",
                category="Visa",
                assigned=Decimal("250.00"),
            ),
            YNABBudgetEntry(
                month=JAN5.replace(day=1),
                category_group="Credit Card Payments",
                category="Skipped Amex",
                assigned=Decimal("75.00"),
            ),
        ],
    )
    result = await _importer(
        services, db_session, budget, account_types={"Visa": ("credit_card", True)}
    ).import_budget(data)

    assert result.credit_card_payment_assignments_skipped == 1
    assert result.credit_card_payment_reserves_skipped == Decimal("75.00")

    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    linked = await services.category_repo.get_by_linked_account(accounts["Visa"].id)
    assert linked is not None
    assignments = await services.assignment_repo.get_all_for_budget(budget.id)
    by_cat = {(a.category_id, a.month): a.assigned for a in assignments}
    assert by_cat[(linked.id, JAN5.replace(day=1))] == Decimal("250.00")
    # No visible "Credit Card Payments" spending group was created for it.
    # The group is live, not archived — it is the app's plumbing, and the
    # archived listing is the user's own envelopes. What keeps it off the grid
    # is `is_card_only`; what keeps its envelopes out of the pickers is
    # `IS_ASSIGNABLE` naming `LINKED_TO_CARD`. It leaned on the archived flag
    # for both until those were made to say so themselves.
    groups = await CategoryGroupRepository(db_session).get_all(budget.id, include_archived=True)
    ccp = [g for g in groups if g.name == "Credit Card Payments"]
    assert len(ccp) == 1
    assert ccp[0].is_archived is False
    assert ccp[0].is_card_only is True
    assert (await services.category_repo.get(linked.id)).is_assignable is False
