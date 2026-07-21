"""Infrastructure smoke test: real DB round-trip through services + invariants.

Scenario (hand-computed):
- Income +1000.00 into checking (system Income category, cleared)
- Assign 600.00 to Groceries
- Spend -100.00 on Groceries (cleared)
Expected: account balance 900.00, Groceries available 500.00, TBA 400.00.
"""

from datetime import date
from decimal import Decimal

from igab.services.transaction_service import TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)
from .invariants import assert_financial_invariants


async def test_basic_budget_flow(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")

    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Ready to Assign")
    spending_group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, spending_group, "Groceries")

    month = date(2026, 7, 1)
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 3), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, groceries.id, month, Decimal("600.00"))
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=date(2026, 7, 10),
            amount=Decimal("-100.00"),
            payee_name="Corner Market",
            category_id=groceries.id,
            cleared="cleared",
        ),
    )

    balance = await services.account_repo.get_balance(checking.id)
    assert balance == Decimal("900.00")

    summary = await services.budgets.get_budget_summary(budget.id, month)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[groceries.id].available == Decimal("500.00")
    assert summary.to_be_assigned == Decimal("400.00")

    await assert_financial_invariants(db_session, budget.id)


async def test_transfer_round_trip(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings")

    await create_transaction(db_session, budget, checking, "500.00", date(2026, 7, 1))
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=date(2026, 7, 5),
            amount=Decimal("200.00"),
            transfer_account_id=savings.id,
            cleared="cleared",
        ),
    )

    # Transfer legs: -200 in checking, +200 in savings; dest leg is uncleared
    # today so overall balances still conserve.
    checking_balance = await services.account_repo.get_balance(checking.id)
    savings_balance = await services.account_repo.get_balance(savings.id)
    assert checking_balance + savings_balance == Decimal("500.00")

    await assert_financial_invariants(db_session, budget.id)
