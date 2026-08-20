"""Phase 4 spec: YNAB import is fully idempotent — including transfers —
with per-leg cleared state preserved and both legs linked."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Transaction
from igab.integrations.ynab.importer import YNABImporter
from igab.integrations.ynab.models import YNABBudget, YNABSplitLeg, YNABTransaction
from igab.repositories.category_repo import CategoryGroupRepository

from .factories import create_budget, create_user, make_services
from .invariants import assert_financial_invariants

JAN5 = date(2026, 1, 5)


def _importer(services, db_session, budget, account_types=None, skip_accounts=None) -> YNABImporter:
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

    data = YNABBudget(
        transactions=[_txn("Checking", "Transfer : Old Closed Account", "-75.00")]
    )
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
    rows = await db_session.execute(
        select(Transaction).where(Transaction.account_id == account_id)
    )
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
    assert await services.account_repo.get_balance(accounts["Checking"].id) == Decimal(
        "-154.90"
    )
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
            _txn(
                "Checking", "Corner Market", "-50.00", group="Everyday", category="Groceries"
            ),
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
    assert await services.account_repo.get_balance(accounts["Checking"].id) == Decimal(
        "-100.00"
    )
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
            (await db_session.execute(select(Transaction).where(Transaction.budget_id == budget.id)))
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
            (await db_session.execute(select(Transaction).where(Transaction.budget_id == budget.id)))
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
            await db_session.execute(
                select(Transaction).where(Transaction.budget_id == budget.id)
            )
        ).scalars().all()
        assert len(count) == len(data.transactions)
        await assert_financial_invariants(db_session, budget.id)
