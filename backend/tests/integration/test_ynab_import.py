"""Phase 4 spec: YNAB import is fully idempotent — including transfers —
with per-leg cleared state preserved and both legs linked."""

from datetime import date
from decimal import Decimal

from igab.integrations.ynab.importer import YNABImporter
from igab.integrations.ynab.models import YNABBudget, YNABTransaction
from igab.repositories.category_repo import CategoryGroupRepository

from .factories import create_budget, create_user, make_services
from .invariants import assert_financial_invariants

JAN5 = date(2026, 1, 5)


def _importer(services, db_session, budget, account_types=None) -> YNABImporter:
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
        account_types={"Brokerage": ("tracking", False)},
    ).import_budget(data)

    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    brokerage = accounts["Brokerage"]
    assert brokerage.account_type == "tracking"
    assert brokerage.on_budget is False
