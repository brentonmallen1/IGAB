"""The three terms of Ready to Assign, each pinned where it used to be wrong.

TBA = cash through the month's end − envelope balances through the month
    − assignments after the month.
"""

from datetime import date
from decimal import Decimal

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

AUG, SEP = date(2026, 8, 1), date(2026, 9, 1)
D = Decimal


async def _budget(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    bills = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, bills, "Rent")
    await create_transaction(db_session, budget, checking, "3000.00", date(2026, 8, 2), category=inflow)
    await create_budget_assignment(db_session, budget, rent, AUG, "1200.00")
    await create_transaction(db_session, budget, checking, "-1200.00", date(2026, 8, 5), category=rent)
    return services, budget, checking, inflow, rent


async def _tba(services, budget, month):
    return (await services.budgets.get_budget_summary(budget.id, month)).to_be_assigned


async def test_closing_an_account_with_a_balance_leaves_ready_to_assign_unchanged(db_session):
    """Only a transaction moves money. The import offers to close every
    dormant account, and each one closed used to take its balance with it."""
    services, budget, checking, inflow, _ = await _budget(db_session)
    dormant = await create_account(db_session, budget, "Old Savings")
    await create_transaction(db_session, budget, dormant, "900.00", date(2025, 1, 15), category=inflow)
    assert await _tba(services, budget, AUG) == D("2700.00")

    await services.account_repo.update(dormant.id, is_closed=True)
    assert await _tba(services, budget, AUG) == D("2700.00")
    assert await services.account_repo.get_balance(dormant.id) == D("900.00")


async def test_a_future_dated_row_counts_in_its_own_month(db_session):
    """An uncategorized outflow dated next month lowers next month's figure —
    it reaches no envelope, so it comes straight out of Ready to Assign —
    and leaves this month's alone. The account header still shows it."""
    services, budget, checking, _, _ = await _budget(db_session)
    assert await _tba(services, budget, AUG) == D("1800.00")
    await create_transaction(db_session, budget, checking, "-400.00", date(2026, 9, 3))

    assert await _tba(services, budget, AUG) == D("1800.00")
    assert await _tba(services, budget, SEP) == D("1400.00")
    assert await services.account_repo.get_balance(checking.id) == D("1400.00")


async def test_ready_to_assign_agrees_across_months_when_next_months_spending_is_covered(
    db_session,
):
    """A September expense with a September assignment behind it: August and
    September show the same figure — the invariant the future-assignment
    deduction exists for, now that the balance term is bounded too."""
    services, budget, checking, _, rent = await _budget(db_session)
    await create_budget_assignment(db_session, budget, rent, SEP, "1200.00")
    await create_transaction(db_session, budget, checking, "-1200.00", date(2026, 9, 5), category=rent)
    assert await _tba(services, budget, AUG) == D("600.00")
    assert await _tba(services, budget, SEP) == D("600.00")


async def test_a_future_assignment_on_an_income_category_is_not_deducted(db_session):
    """Refused now, but rows written before that exist. The category term
    leaves income categories out; the future term must too."""
    services, budget, _, inflow, _ = await _budget(db_session)
    await create_budget_assignment(db_session, budget, inflow, SEP, "999.00")
    assert await _tba(services, budget, AUG) == D("1800.00")
