"""Transfers to off-budget accounts: the on-budget leg may carry a category,
which flows into category activity; on-budget↔on-budget transfers never can.

Where IGAB now departs from YNAB: such a leg is no longer *spending*. Moving
money to a brokerage or a mortgage leaves the budget, but it builds net worth
rather than consuming it, so spending reports exclude it by default and offer
it back behind `include_savings`. Category activity is unchanged — the money
did leave the envelope.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.activity_class import ActivityClass
from igab.domain.exceptions import InvariantViolation
from igab.services.report_service import ReportService
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

TODAY = date.today()
MONTH = TODAY.replace(day=1)


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    mortgage = await create_account(
        db_session, budget, "Mortgage", account_type="loan", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Obligations")
    housing = await create_category(db_session, budget, group, "Housing")
    return services, budget, checking, mortgage, housing


async def test_categorized_offbudget_transfer_hits_category_activity(db_session):
    services, budget, checking, mortgage, housing = await _setup(db_session)
    await create_transaction(db_session, budget, checking, "2000.00", TODAY - timedelta(days=5))
    await services.budgets.set_assignment(budget.id, housing.id, MONTH, Decimal("1500.00"))

    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("1200.00"),
            transfer_account_id=mortgage.id,
            category_id=housing.id,
            cleared="cleared",
        ),
    )

    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    by_cat = {b.category_id: b for b in summary.category_balances}
    assert by_cat[housing.id].activity == Decimal("-1200.00"), (
        "the on-budget leg of an off-budget transfer is category spending"
    )
    assert by_cat[housing.id].available == Decimal("300.00")
    # TBA: 800 in checking (2000-1200), 300 enveloped → 500
    assert summary.to_be_assigned == Decimal("500.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_categorized_offbudget_transfer_in_spending_reports(db_session):
    services, budget, checking, mortgage, housing = await _setup(db_session)
    reports = ReportService(db_session)

    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("1200.00"),
            transfer_account_id=mortgage.id,
            category_id=housing.id,
            cleared="cleared",
        ),
    )

    # Paying down a tracked mortgage is debt principal, not spending.
    categories, _ = await reports.spending_by_category(budget.id, TODAY - timedelta(days=30), TODAY)
    assert "Housing" not in {c["name"] for c in categories}, (
        "a mortgage payment is not spending — this is the skew derkus reported"
    )

    # Still reachable for anyone who wants the fuller picture.
    categories, _ = await reports.spending_by_category(
        budget.id,
        TODAY - timedelta(days=30),
        TODAY,
        include_classes=[ActivityClass.SPENDING, ActivityClass.DEBT_PRINCIPAL],
    )
    by_name = {c["name"]: c["total"] for c in categories}
    assert by_name.get("Housing") == Decimal("1200.0")

    # Cash flow agrees: the mortgage payment is debt principal, not expense.
    results = await reports.income_vs_expense(budget.id, months=1)
    assert results[-1]["expenses"] == Decimal("0")
    assert results[-1]["debt_principal"] == Decimal("1200.00")
    assert results[-1]["income"] == Decimal("0")


async def test_onbudget_transfer_with_category_rejected(db_session):
    services, budget, checking, mortgage, housing = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")

    with pytest.raises(InvariantViolation, match="off-budget"):
        await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=TODAY,
                amount=Decimal("100.00"),
                transfer_account_id=savings.id,
                category_id=housing.id,
                cleared="cleared",
            ),
        )


async def test_uncategorized_onbudget_transfer_still_excluded_from_cash_flow(db_session):
    services, budget, checking, mortgage, housing = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")
    reports = ReportService(db_session)

    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("300.00"),
            transfer_account_id=savings.id,
            cleared="cleared",
        ),
    )

    results = await reports.income_vs_expense(budget.id, months=1)
    assert results[-1]["expenses"] == Decimal("0")
    assert results[-1]["income"] == Decimal("0")


async def test_uncategorized_offbudget_leg_counts_as_uncategorized(db_session):
    services, budget, checking, mortgage, housing = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")

    # Off-budget transfer without category: needs the user's attention
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("500.00"),
            transfer_account_id=mortgage.id,
            cleared="cleared",
        ),
    )
    # On-budget transfer: never needs a category
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("100.00"),
            transfer_account_id=savings.id,
            cleared="cleared",
        ),
    )

    count = await services.account_repo.get_uncategorized_count(checking.id)
    assert count == 1, "only the off-budget leg needs categorization"
