"""Phase 1 spec: pending transactions are provisional and must not move any
money aggregate — not the account balance (already true), not category
activity, not TBA. Posting is the single event where money moves.
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

MONTH = date(2026, 7, 1)


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("600.00"))
    return services, budget, checking, groceries


async def test_pending_txn_moves_neither_balance_nor_activity(db_session):
    services, budget, checking, groceries = await _setup(db_session)

    pending = await create_transaction(
        db_session,
        budget,
        checking,
        "-50.00",
        date(2026, 7, 10),
        category=groceries,
        cleared="pending",
    )

    assert await services.account_repo.get_balance(checking.id) == Decimal("1000.00")
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[groceries.id].activity == Decimal("0"), (
        "pending outflow leaked into category activity"
    )
    assert by_cat[groceries.id].available == Decimal("600.00")
    assert summary.to_be_assigned == Decimal("400.00")

    # Posting is the single event where the money moves — both sides at once.
    await services.transaction_repo.update_cleared(pending.id, "cleared")
    assert await services.account_repo.get_balance(checking.id) == Decimal("950.00")
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[groceries.id].activity == Decimal("-50.00")
    assert by_cat[groceries.id].available == Decimal("550.00")
    assert summary.to_be_assigned == Decimal("400.00")

    await assert_financial_invariants(db_session, budget.id)


async def test_pending_split_children_mirror_parent_and_stay_excluded(db_session):
    services, budget, checking, groceries = await _setup(db_session)

    header = TransactionCreate(
        account_id=checking.id,
        date=date(2026, 7, 12),
        amount=Decimal("-80.00"),
        cleared="pending",
    )
    splits = [
        TransactionCreate(
            account_id=checking.id,
            date=date(2026, 7, 12),
            amount=Decimal("-80.00"),
            category_id=groceries.id,
        )
    ]
    await services.transactions.create_split(budget.id, header, splits)

    assert await services.account_repo.get_balance(checking.id) == Decimal("1000.00")
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[groceries.id].activity == Decimal("0"), (
        "pending split's children counted in activity while the parent is "
        "excluded from the account balance"
    )
    assert summary.to_be_assigned == Decimal("400.00")

    await assert_financial_invariants(db_session, budget.id)
