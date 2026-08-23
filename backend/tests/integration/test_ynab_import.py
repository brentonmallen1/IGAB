"""Phase 4 spec: YNAB import is fully idempotent — including transfers —
with per-leg cleared state preserved and both legs linked."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from igab.db.models import Account, Transaction
from igab.integrations.ynab.importer import YNABImporter
from igab.integrations.ynab.models import YNABBudget, YNABSplitLeg, YNABTransaction
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
    spending). The leg imports with its category and is not transfer-linked
    (linked categorized transfers arrive with the off-budget feature)."""
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
