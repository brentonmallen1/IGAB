"""Phase 1 spec for report math: transfers and pending excluded, split
children included wherever categories are aggregated.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.services.report_service import ReportService
from igab.services.transaction_service import TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()
START = TODAY - timedelta(days=20)


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    gas = await create_category(db_session, budget, everyday, "Gas")
    return services, budget, checking, savings, groceries, gas


async def test_income_vs_expense_excludes_transfers_and_pending(db_session):
    services, budget, checking, savings, groceries, gas = await _setup(db_session)
    reports = ReportService(db_session)

    payee = await create_payee(db_session, budget, "Employer")
    await create_transaction(
        db_session, budget, checking, "500.00", TODAY - timedelta(days=5), payee=payee
    )
    await create_transaction(
        db_session, budget, checking, "-200.00", TODAY - timedelta(days=4), category=groceries
    )
    # On-budget transfer: must not count as income or expense
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=3),
            amount=Decimal("150.00"),
            transfer_account_id=savings.id,
            cleared="cleared",
        ),
    )
    # Pending expense: provisional, must not count yet
    await create_transaction(
        db_session,
        budget,
        checking,
        "-75.00",
        TODAY - timedelta(days=2),
        category=gas,
        cleared="pending",
    )

    results = await reports.income_vs_expense(budget.id, months=1)
    this_month = results[-1]
    assert this_month["income"] == Decimal("500.0")
    assert this_month["expenses"] == Decimal("200.0")


async def test_spending_by_category_includes_split_children(db_session):
    services, budget, checking, savings, groceries, gas = await _setup(db_session)
    reports = ReportService(db_session)

    header = TransactionCreate(
        account_id=checking.id,
        date=TODAY - timedelta(days=5),
        amount=Decimal("-100.00"),
        cleared="cleared",
    )
    splits = [
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=5),
            amount=Decimal("-60.00"),
            category_id=groceries.id,
        ),
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=5),
            amount=Decimal("-40.00"),
            category_id=gas.id,
        ),
    ]
    await services.transactions.create_split(budget.id, header, splits)

    categories, grand_total = await reports.spending_by_category(budget.id, START, TODAY)
    by_name = {c["name"]: c["total"] for c in categories}
    assert by_name.get("Groceries") == Decimal("60.0")
    assert by_name.get("Gas") == Decimal("40.0")
    assert grand_total == Decimal("100.0")


async def test_budget_vs_actual_and_grouped_include_split_children(db_session):
    services, budget, checking, savings, groceries, gas = await _setup(db_session)
    reports = ReportService(db_session)

    header = TransactionCreate(
        account_id=checking.id,
        date=TODAY - timedelta(days=5),
        amount=Decimal("-100.00"),
        cleared="cleared",
    )
    splits = [
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=5),
            amount=Decimal("-60.00"),
            category_id=groceries.id,
        ),
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=5),
            amount=Decimal("-40.00"),
            category_id=gas.id,
        ),
    ]
    await services.transactions.create_split(budget.id, header, splits)

    bva = await reports.budget_vs_actual(budget.id, START, TODAY)
    spent_by_cat = {c["category_id"]: c["spent"] for c in bva["categories"]}
    assert spent_by_cat.get(str(groceries.id)) == Decimal("60.00")
    assert spent_by_cat.get(str(gas.id)) == Decimal("40.00")
    assert bva["total_spent"] == Decimal("100.00")

    items, total = await reports.spending_grouped(budget.id, START, TODAY)
    grouped = {i["name"]: i["total"] for i in items}
    assert grouped.get("Groceries") == Decimal("60.0")
    assert grouped.get("Gas") == Decimal("40.0")


async def test_dashboard_top_categories_include_children_net_worth_parent_based(db_session):
    services, budget, checking, savings, groceries, gas = await _setup(db_session)
    reports = ReportService(db_session)

    await create_transaction(
        db_session, budget, checking, "1000.00", TODAY - timedelta(days=10)
    )
    header = TransactionCreate(
        account_id=checking.id,
        date=TODAY - timedelta(days=5),
        amount=Decimal("-100.00"),
        cleared="cleared",
    )
    splits = [
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=5),
            amount=Decimal("-60.00"),
            category_id=groceries.id,
        ),
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=5),
            amount=Decimal("-40.00"),
            category_id=gas.id,
        ),
    ]
    await services.transactions.create_split(budget.id, header, splits)

    metrics = await reports.dashboard_metrics(budget.id, START, TODAY)
    assert metrics["net_worth"] == Decimal("900.0")
    top = {c["name"]: c["total"] for c in metrics["top_categories"]}
    assert top.get("Groceries") == Decimal("60.0")
    assert top.get("Gas") == Decimal("40.0")


async def test_float_boundary_amounts_stay_exact_decimals(db_session):
    """0.10 + 0.20 must never surface as 0.30000000000000004 in any report."""
    services, budget, checking, savings, groceries, gas = await _setup(db_session)
    reports = ReportService(db_session)

    # All dated today so the scenario never straddles a month boundary
    await create_transaction(db_session, budget, checking, "-0.10", TODAY, category=groceries)
    await create_transaction(db_session, budget, checking, "-0.20", TODAY, category=groceries)
    await create_transaction(db_session, budget, checking, "0.10", TODAY)
    await create_transaction(db_session, budget, checking, "0.20", TODAY)

    categories, grand_total = await reports.spending_by_category(budget.id, START, TODAY)
    assert grand_total == Decimal("0.30")
    assert categories[0]["total"] == Decimal("0.30")

    items, grouped_total = await reports.spending_grouped(budget.id, START, TODAY)
    assert grouped_total == Decimal("0.30")
    assert items[0]["total"] == Decimal("0.30")

    this_month = (await reports.income_vs_expense(budget.id, months=1))[-1]
    assert this_month["income"] == Decimal("0.30")
    assert this_month["expenses"] == Decimal("0.30")
    assert this_month["net"] == Decimal("0.00")


async def test_cash_flow_sankey_includes_split_children(db_session):
    services, budget, checking, savings, groceries, gas = await _setup(db_session)
    reports = ReportService(db_session)

    header = TransactionCreate(
        account_id=checking.id,
        date=TODAY - timedelta(days=5),
        amount=Decimal("-100.00"),
        payee_name="Superstore",
        cleared="cleared",
    )
    splits = [
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=5),
            amount=Decimal("-60.00"),
            payee_name="Superstore",
            category_id=groceries.id,
        ),
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=5),
            amount=Decimal("-40.00"),
            payee_name="Superstore",
            category_id=gas.id,
        ),
    ]
    await services.transactions.create_split(budget.id, header, splits)

    sankey = await reports.cash_flow_sankey(budget.id, START, TODAY, mode="spent")
    link_values = {
        (link["source"], link["target"]): link["value"] for link in sankey["links"]
    }
    assert link_values.get(
        (f"g_{groceries.category_group_id}", f"c_{groceries.id}")
    ) == Decimal("60.0")
    assert link_values.get((f"g_{gas.category_group_id}", f"c_{gas.id}")) == Decimal("40.0")
    assert sankey["total_expense"] == Decimal("100.0")
