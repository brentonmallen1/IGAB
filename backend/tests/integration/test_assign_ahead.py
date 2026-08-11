"""Assigning ahead (B1): dollars committed to a future month must reduce the
current month's TBA — otherwise the same dollars could be assigned twice —
and the months endpoint must expose the deduction so the UI can explain it.
"""

from datetime import date
from decimal import Decimal

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    make_services,
)

JUL = date(2026, 7, 1)
AUG = date(2026, 8, 1)
SEP = date(2026, 9, 1)


async def _setup(db_session, user):
    services = make_services(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=income_cat
    )
    return services, budget, groceries


async def test_future_assignment_reduces_earlier_months_tba(db_session, api_client):
    services, budget, groceries = await _setup(db_session, api_client.test_user)
    await services.budgets.set_assignment(budget.id, groceries.id, SEP, Decimal("500.00"))

    for month, expected_future in ((JUL, "500.00"), (AUG, "500.00")):
        resp = await api_client.get(f"/api/v1/{budget.id}/months/{month.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["to_be_assigned"])) == Decimal("500.00"), month
        assert Decimal(str(data["assigned_in_future"])) == Decimal(expected_future), month

    # In September itself the money sits in the category, not in the future
    resp = await api_client.get(f"/api/v1/{budget.id}/months/{SEP.isoformat()}")
    data = resp.json()
    assert Decimal(str(data["to_be_assigned"])) == Decimal("500.00")
    assert Decimal(str(data["assigned_in_future"])) == Decimal("0")


async def test_assign_ahead_then_assign_current_month_cannot_double_spend(db_session, api_client):
    """The classic bug: assign $500 to September, navigate back to July, TBA
    must show $500 — assigning another $600 in July then overdraws visibly."""
    services, budget, groceries = await _setup(db_session, api_client.test_user)
    await services.budgets.set_assignment(budget.id, groceries.id, SEP, Decimal("500.00"))
    await services.budgets.set_assignment(budget.id, groceries.id, JUL, Decimal("600.00"))

    summary = await services.budgets.get_budget_summary(budget.id, JUL)
    assert summary.to_be_assigned == Decimal("-100.00")
    assert summary.assigned_in_future == Decimal("500.00")


async def test_clearing_future_assignment_restores_tba(db_session, api_client):
    services, budget, groceries = await _setup(db_session, api_client.test_user)
    await services.budgets.set_assignment(budget.id, groceries.id, SEP, Decimal("500.00"))
    await services.budgets.set_assignment(budget.id, groceries.id, SEP, Decimal("0"))

    summary = await services.budgets.get_budget_summary(budget.id, JUL)
    assert summary.to_be_assigned == Decimal("1000.00")
    assert summary.assigned_in_future == Decimal("0")
