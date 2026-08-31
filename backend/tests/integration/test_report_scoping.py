"""Cash-flow reports default to on-budget accounts.

Plain activity inside tracking accounts (market gains, loan interest) moves
net worth, never budget income/expense. Categorized spending-transfer legs
live on the on-budget side and still count. An explicit account filter
overrides the default scope.
"""

from datetime import date
from decimal import Decimal

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
)

TODAY = date.today()
IN_MONTH = TODAY.replace(day=1)


async def _setup(db_session, owner):
    budget = await create_budget(db_session, owner)
    checking = await create_account(db_session, budget, "Checking")
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    investing = await create_category(db_session, budget, group, "Investing")

    # On-budget cash flow
    await create_transaction(db_session, budget, checking, "1000.00", IN_MONTH)  # paycheck
    await create_transaction(db_session, budget, checking, "-100.00", IN_MONTH, category=groceries)
    # Categorized spending transfer to the brokerage: the categorized leg sits
    # on the on-budget side and counts as an expense
    leg_out = await create_transaction(
        db_session, budget, checking, "-500.00", IN_MONTH, category=investing
    )
    leg_in = await create_transaction(
        db_session, budget, brokerage, "500.00", IN_MONTH, transfer_id=leg_out.id
    )
    leg_out.transfer_id = leg_in.id
    # Plain off-budget activity: a market gain and a fee — net worth only
    await create_transaction(db_session, budget, brokerage, "800.00", IN_MONTH)
    await create_transaction(db_session, budget, brokerage, "-50.00", IN_MONTH)
    await db_session.flush()
    return budget, checking, brokerage


async def test_income_expense_excludes_off_budget_activity(api_client, db_session):
    budget, _, _ = await _setup(db_session, api_client.test_user)

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/income-expense", params={"months": 1})
    assert resp.status_code == 200
    month = resp.json()["months"][-1]
    # 1000 paycheck only — the 800 market gain is not income
    assert Decimal(month["income"]) == Decimal("1000.00")
    # 100 groceries. The 500 transfer to the brokerage is saving, not spending,
    # and the 50 brokerage fee is off-budget so never in scope at all.
    assert Decimal(month["expenses"]) == Decimal("100.00")
    assert Decimal(month["savings"]) == Decimal("500.00")


async def test_spending_excludes_a_transfer_into_savings(api_client, db_session):
    """Money moved to the brokerage is saving, not spending. Leaving it in
    inflates every spending average — the complaint that motivated this."""
    budget, _, _ = await _setup(db_session, api_client.test_user)

    resp = await api_client.get(
        f"/api/v1/{budget.id}/reports/spending",
        params={"start_date": IN_MONTH.isoformat(), "end_date": TODAY.isoformat()},
    )
    assert resp.status_code == 200
    by_name = {c["name"]: Decimal(c["total"]) for c in resp.json()["categories"]}
    assert by_name["Groceries"] == Decimal("100.00")
    assert "Investing" not in by_name


async def test_include_savings_brings_the_transfer_back(api_client, db_session):
    budget, _, _ = await _setup(db_session, api_client.test_user)

    resp = await api_client.get(
        f"/api/v1/{budget.id}/reports/spending",
        params={
            "start_date": IN_MONTH.isoformat(),
            "end_date": TODAY.isoformat(),
            "include_savings": "true",
        },
    )
    by_name = {c["name"]: Decimal(c["total"]) for c in resp.json()["categories"]}
    assert by_name["Investing"] == Decimal("500.00")
    assert by_name["Groceries"] == Decimal("100.00")


async def test_explicit_account_filter_overrides_default_scope(api_client, db_session):
    budget, _, brokerage = await _setup(db_session, api_client.test_user)

    # Default: the timeline never shows plain off-budget rows
    resp = await api_client.get(
        f"/api/v1/{budget.id}/reports/large-transactions",
        params={"start_date": IN_MONTH.isoformat(), "end_date": TODAY.isoformat()},
    )
    amounts = [Decimal(t["amount"]) for t in resp.json()["transactions"]]
    assert Decimal("-50.00") not in amounts

    # Explicitly selecting the brokerage wins over the default
    resp = await api_client.get(
        f"/api/v1/{budget.id}/reports/large-transactions",
        params={
            "start_date": IN_MONTH.isoformat(),
            "end_date": TODAY.isoformat(),
            "account_ids": str(brokerage.id),
        },
    )
    amounts = [Decimal(t["amount"]) for t in resp.json()["transactions"]]
    assert Decimal("-50.00") in amounts
    assert Decimal("-100.00") not in amounts
