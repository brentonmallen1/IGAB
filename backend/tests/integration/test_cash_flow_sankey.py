"""Cash-flow sankey: money in -> budget -> groups -> categories.

Spent mode pins the flow-conservation invariant: the links leaving the
budget node sum exactly to total_expense. Uncategorized spending gets its
own "Uncategorized" flow rather than silently inflating the total, and all
values are exact Decimals (no float representation artifacts).

Budgeted mode draws the same diagram from budget assignments: negative and
zero assignments, system groups, and deleted categories are invisible;
income still comes from real transactions.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.services.report_service import ReportService
from igab.services.transaction_service import TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()
START = TODAY - timedelta(days=20)


def months_ago(n: int) -> date:
    year, month = TODAY.year, TODAY.month - n
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    gas = await create_category(db_session, budget, everyday, "Gas")
    return services, budget, checking, everyday, groceries, gas


async def test_spent_mode_links_sum_to_total_expense(db_session):
    services, budget, checking, everyday, groceries, gas = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")
    brokerage = await create_account(db_session, budget, "Brokerage", on_budget=False)

    employer = await create_payee(db_session, budget, "Employer")
    megamart = await create_payee(db_session, budget, "MegaMart")
    corner = await create_payee(db_session, budget, "CornerStore")

    await create_transaction(
        db_session, budget, checking, "3000.00", TODAY - timedelta(days=5), payee=employer
    )
    await create_transaction(
        db_session, budget, checking, "-200.00", TODAY - timedelta(days=4),
        category=groceries, payee=megamart,
    )
    await create_transaction(
        db_session, budget, checking, "-100.00", TODAY - timedelta(days=4), category=gas
    )
    # Categorized transfer to an off-budget account: real spending
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=3),
            amount=Decimal("-150.00"),
            transfer_account_id=brokerage.id,
            category_id=groceries.id,
            cleared="cleared",
        ),
    )
    # Uncategorized on-budget transfer: internal, invisible here
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=3),
            amount=Decimal("-150.00"),
            transfer_account_id=savings.id,
            cleared="cleared",
        ),
    )
    # Pending: not posted yet
    await create_transaction(
        db_session, budget, checking, "-75.00", TODAY - timedelta(days=2),
        category=groceries, cleared="pending",
    )
    # Split: children flow to their categories, parent must not double-count
    header = TransactionCreate(
        account_id=checking.id,
        date=TODAY - timedelta(days=2),
        amount=Decimal("-100.00"),
        payee_name="Superstore",
        cleared="cleared",
    )
    splits = [
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=2),
            amount=Decimal("-60.00"),
            payee_name="Superstore",
            category_id=groceries.id,
        ),
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=2),
            amount=Decimal("-40.00"),
            payee_name="Superstore",
            category_id=gas.id,
        ),
    ]
    await services.transactions.create_split(budget.id, header, splits)
    # Uncategorized cash spending: must appear as its own flow
    await create_transaction(
        db_session, budget, checking, "-33.33", TODAY - timedelta(days=1), payee=corner
    )

    sankey = await ReportService(db_session).cash_flow_sankey(
        budget.id, START, TODAY, mode="spent"
    )

    assert sankey["total_income"] == Decimal("3000.00")
    # 200 + 100 + 150 transfer + 100 split + 33.33 uncategorized
    assert sankey["total_expense"] == Decimal("583.33")

    links = {(link["source"], link["target"]): link["value"] for link in sankey["links"]}
    assert links[(f"inc_{employer.id}", "__budget__")] == Decimal("3000.00")
    assert links[("__budget__", f"g_{everyday.id}")] == Decimal("550.00")
    assert links[(f"g_{everyday.id}", f"c_{groceries.id}")] == Decimal("410.00")
    assert links[(f"g_{everyday.id}", f"c_{gas.id}")] == Decimal("140.00")
    assert links[("__budget__", "g___uncategorized__")] == Decimal("33.33")
    assert links[("g___uncategorized__", "c___uncategorized__")] == Decimal("33.33")

    # Flow conservation: budget outflows account for every expense dollar
    budget_outflows = sum(v for (src, _), v in links.items() if src == "__budget__")
    assert budget_outflows == sankey["total_expense"]

    names = {n["id"]: n["name"] for n in sankey["nodes"]}
    assert names["g___uncategorized__"] == "Uncategorized"
    grocery_payees = {
        p["name"]: p["total"] for p in sankey["category_payees"][f"c_{groceries.id}"]
    }
    assert grocery_payees["MegaMart"] == Decimal("200.00")
    assert grocery_payees["Superstore"] == Decimal("60.00")
    uncat_payees = {
        p["name"]: p["total"] for p in sankey["category_payees"]["c___uncategorized__"]
    }
    assert uncat_payees["CornerStore"] == Decimal("33.33")


async def test_spent_mode_totals_are_exact_decimals(db_session):
    services, budget, checking, everyday, groceries, gas = await _setup(db_session)

    for _ in range(3):
        await create_transaction(
            db_session, budget, checking, "-0.10", TODAY - timedelta(days=2), category=groceries
        )
    await create_transaction(db_session, budget, checking, "0.10", TODAY - timedelta(days=3))
    await create_transaction(db_session, budget, checking, "0.20", TODAY - timedelta(days=3))

    sankey = await ReportService(db_session).cash_flow_sankey(
        budget.id, START, TODAY, mode="spent"
    )

    assert sankey["total_expense"] == Decimal("0.30")
    assert str(sankey["total_expense"]) != "0.30000000000000004"
    assert sankey["total_income"] == Decimal("0.30")


async def test_spent_mode_account_filter(db_session):
    services, budget, checking, everyday, groceries, gas = await _setup(db_session)
    other = await create_account(db_session, budget, "Other")

    await create_transaction(
        db_session, budget, checking, "-50.00", TODAY - timedelta(days=2), category=groceries
    )
    await create_transaction(
        db_session, budget, other, "-70.00", TODAY - timedelta(days=2), category=groceries
    )

    sankey = await ReportService(db_session).cash_flow_sankey(
        budget.id, START, TODAY, mode="spent", account_ids=[checking.id]
    )

    assert sankey["total_expense"] == Decimal("50.00")


async def test_budgeted_mode_draws_positive_assignments_only(db_session):
    services, budget, checking, everyday, groceries, gas = await _setup(db_session)
    dining = await create_category(db_session, budget, everyday, "Dining")
    zeroed = await create_category(db_session, budget, everyday, "Zeroed")
    sys_group = await create_category_group(db_session, budget, "Hidden", is_system=True)
    sys_cat = await create_category(db_session, budget, sys_group, "System Cat")
    ghost = await create_category(db_session, budget, everyday, "Ghost")

    month = TODAY.replace(day=1)
    await create_budget_assignment(db_session, budget, groceries, month, "500.00")
    await create_budget_assignment(db_session, budget, gas, month, "200.00")
    await create_budget_assignment(db_session, budget, dining, month, "-50.00")
    await create_budget_assignment(db_session, budget, zeroed, month, "0.00")
    await create_budget_assignment(db_session, budget, sys_cat, month, "100.00")
    await create_budget_assignment(db_session, budget, ghost, month, "100.00")
    ghost.is_deleted = True
    await db_session.flush()
    # Income comes from transactions even in budgeted mode
    await create_transaction(db_session, budget, checking, "1000.00", TODAY)

    sankey = await ReportService(db_session).cash_flow_sankey(
        budget.id, month, TODAY, mode="budgeted"
    )

    assert sankey["total_income"] == Decimal("1000.00")
    assert sankey["total_expense"] == Decimal("700.00")
    links = {(link["source"], link["target"]): link["value"] for link in sankey["links"]}
    assert links[("__budget__", f"g_{everyday.id}")] == Decimal("700.00")
    assert links[(f"g_{everyday.id}", f"c_{groceries.id}")] == Decimal("500.00")
    assert links[(f"g_{everyday.id}", f"c_{gas.id}")] == Decimal("200.00")
    assert len(links) == 3
    assert sankey["category_payees"] == {}


async def test_budgeted_mode_account_filter_applies_to_income(db_session):
    """Assignments have no account dimension, but the income total is
    transaction-derived and must honor the account filter like spent mode."""
    services, budget, checking, everyday, groceries, gas = await _setup(db_session)
    other = await create_account(db_session, budget, "Other")

    month = TODAY.replace(day=1)
    await create_budget_assignment(db_session, budget, groceries, month, "500.00")
    await create_transaction(db_session, budget, checking, "1000.00", TODAY)
    await create_transaction(db_session, budget, other, "250.00", TODAY)

    sankey = await ReportService(db_session).cash_flow_sankey(
        budget.id, month, TODAY, mode="budgeted", account_ids=[checking.id]
    )

    assert sankey["total_income"] == Decimal("1000.00")
    # Assignment flows are budget-level and stay unfiltered
    assert sankey["total_expense"] == Decimal("500.00")
    links = {(link["source"], link["target"]): link["value"] for link in sankey["links"]}
    assert links[(f"g_{everyday.id}", f"c_{groceries.id}")] == Decimal("500.00")


async def test_budgeted_mode_sums_across_months(db_session):
    services, budget, checking, everyday, groceries, gas = await _setup(db_session)

    await create_budget_assignment(db_session, budget, groceries, months_ago(1), "500.00")
    await create_budget_assignment(db_session, budget, groceries, months_ago(0), "500.00")

    sankey = await ReportService(db_session).cash_flow_sankey(
        budget.id, months_ago(1), TODAY, mode="budgeted"
    )

    assert sankey["total_expense"] == Decimal("1000.00")
    links = {(link["source"], link["target"]): link["value"] for link in sankey["links"]}
    assert links[(f"g_{everyday.id}", f"c_{groceries.id}")] == Decimal("1000.00")
