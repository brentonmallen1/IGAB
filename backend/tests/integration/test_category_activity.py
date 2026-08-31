"""Phase 1 spec: split transaction spending must flow into category activity.

These tests encode the envelope-math contract with hand-computed literals:
splitting a transaction may never change TBA relative to the same spending
entered as plain transactions, and every child's category sees its share.
"""

from datetime import date
from decimal import Decimal

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
from .invariants import assert_financial_invariants

MONTH = date(2026, 7, 1)


async def _budget_with_categories(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    gas = await create_category(db_session, budget, everyday, "Gas")
    return services, budget, checking, income_cat, groceries, gas


def _split(account_id, total, parts, *, cleared="cleared", payee_name=None):
    header = TransactionCreate(
        account_id=account_id,
        date=date(2026, 7, 10),
        amount=Decimal(total),
        cleared=cleared,
        payee_name=payee_name,
    )
    splits = [
        TransactionCreate(
            account_id=account_id,
            date=date(2026, 7, 10),
            amount=Decimal(amount),
            category_id=category_id,
        )
        for amount, category_id in parts
    ]
    return header, splits


async def test_split_children_count_in_category_activity(db_session):
    services, budget, checking, income_cat, groceries, gas = await _budget_with_categories(
        db_session
    )
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("600.00"))
    await services.budgets.set_assignment(budget.id, gas.id, MONTH, Decimal("100.00"))

    header, splits = _split(checking.id, "-100.00", [("-60.00", groceries.id), ("-40.00", gas.id)])
    await services.transactions.create_split(budget.id, header, splits)

    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}

    assert by_cat[groceries.id].activity == Decimal("-60.00")
    assert by_cat[gas.id].activity == Decimal("-40.00")
    assert by_cat[groceries.id].available == Decimal("540.00")
    assert by_cat[gas.id].available == Decimal("60.00")
    # Envelope spending must not move TBA: 1000 - 100 spent = 900 in the
    # account, 540 + 60 = 600 still enveloped, TBA stays at 300.
    assert summary.to_be_assigned == Decimal("300.00")

    await assert_financial_invariants(db_session, budget.id)


async def test_split_parent_ignores_payee_default_category(db_session):
    services, budget, checking, income_cat, groceries, gas = await _budget_with_categories(
        db_session
    )
    dining_group = await create_category_group(db_session, budget, "Fun")
    dining = await create_category(db_session, budget, dining_group, "Dining")
    await create_payee(db_session, budget, "Superstore", default_category_id=dining.id)

    header, splits = _split(
        checking.id,
        "-100.00",
        [("-60.00", groceries.id), ("-40.00", gas.id)],
        payee_name="Superstore",
    )
    parent = await services.transactions.create_split(budget.id, header, splits)

    assert parent.category_id is None, (
        "split parent must never carry a category (payee default leaked in)"
    )
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[dining.id].activity == Decimal("0")
    assert by_cat[groceries.id].activity == Decimal("-60.00")

    await assert_financial_invariants(db_session, budget.id)


async def test_mixed_sign_split(db_session):
    services, budget, checking, income_cat, groceries, gas = await _budget_with_categories(
        db_session
    )
    header, splits = _split(checking.id, "-50.00", [("-60.00", groceries.id), ("10.00", gas.id)])
    await services.transactions.create_split(budget.id, header, splits)

    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[groceries.id].activity == Decimal("-60.00")
    assert by_cat[gas.id].activity == Decimal("10.00")
    assert await services.account_repo.get_balance(checking.id) == Decimal("-50.00")

    await assert_financial_invariants(db_session, budget.id)


async def test_zero_amount_transaction_and_split_child(db_session):
    services, budget, checking, income_cat, groceries, gas = await _budget_with_categories(
        db_session
    )
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=date(2026, 7, 5),
            amount=Decimal("0.00"),
            category_id=groceries.id,
            cleared="cleared",
        ),
    )
    header, splits = _split(checking.id, "-70.00", [("-70.00", groceries.id), ("0.00", gas.id)])
    await services.transactions.create_split(budget.id, header, splits)

    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[groceries.id].activity == Decimal("-70.00")
    assert by_cat[gas.id].activity == Decimal("0")
    assert await services.account_repo.get_balance(checking.id) == Decimal("-70.00")

    await assert_financial_invariants(db_session, budget.id)


async def test_overspending_via_split_rolls_over_floored(db_session):
    """Month M: assign 600, split-spend 700 -> available -100, TBA untouched.

    Month M+1: category restarts at zero (YNAB flooring), so TBA absorbs the
    overspend: 300 account balance - 0 enveloped = 300.
    """
    services, budget, checking, income_cat, groceries, gas = await _budget_with_categories(
        db_session
    )
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("600.00"))

    header, splits = _split(checking.id, "-700.00", [("-700.00", groceries.id), ("0.00", gas.id)])
    await services.transactions.create_split(budget.id, header, splits)

    july = await services.budgets.get_budget_summary(budget.id, MONTH)
    july_cats = {b.category_id: b for b in july.category_balances}
    assert july_cats[groceries.id].available == Decimal("-100.00")
    # 300 in the account; groceries -100 nets against it: TBA = 300 - (-100)
    assert july.to_be_assigned == Decimal("400.00")

    august = await services.budgets.get_budget_summary(budget.id, date(2026, 8, 1))
    august_cats = {b.category_id: b for b in august.category_balances}
    assert august_cats[groceries.id].available == Decimal("0")
    assert august.to_be_assigned == Decimal("300.00")

    await assert_financial_invariants(db_session, budget.id)
