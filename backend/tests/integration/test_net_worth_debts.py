"""Net worth × debts: unmanaged debts counted exactly once, managed never twice.

The two independent net-worth computations (net_worth_history and the
dashboard metric) must agree — this is the easiest place for the debt
phase to silently corrupt an already-audited number, so both directions
are pinned: an unmanaged debt reduces net worth by exactly its balance,
and creating a Debt row for an on-budget loan account changes nothing.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_debt,
    create_debt_snapshot,
    create_transaction,
    create_user,
)

TODAY = date.today()


async def _net_worth_now(report_svc: ReportService, budget_id) -> tuple[Decimal, Decimal]:
    """(latest history point net worth, dashboard net worth)"""
    history = await report_svc.net_worth_history(budget_id, months=3)
    latest = history[-1]["net_worth"]
    start = TODAY.replace(day=1)
    dashboard = await report_svc.dashboard_metrics(budget_id, start, TODAY)
    return latest, dashboard["net_worth"]


async def test_unmanaged_debt_reduces_net_worth_exactly_once(db_session):
    report_svc = ReportService(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    await create_transaction(db_session, budget, checking, "5000.00", TODAY - timedelta(days=40))

    before_history, before_dashboard = await _net_worth_now(report_svc, budget.id)
    assert before_history == Decimal("5000.00")
    assert before_dashboard == Decimal("5000.00")

    debt = await create_debt(db_session, budget, "Family", manual_balance=Decimal("1200.00"))
    await create_debt_snapshot(db_session, debt, TODAY, Decimal("1200.00"), source="initial")

    after_history, after_dashboard = await _net_worth_now(report_svc, budget.id)
    assert after_history == Decimal("3800.00")
    assert after_dashboard == Decimal("3800.00"), "dashboard must agree with the report"

    history = await report_svc.net_worth_history(budget.id, months=3)
    assert history[-1]["unmanaged_debt_total"] == Decimal("1200.00")
    assert history[-1]["total_liabilities"] == Decimal("1200.00")


async def test_managed_debt_is_not_double_counted(db_session):
    report_svc = ReportService(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    loan = await create_account(db_session, budget, "Loan", account_type="loan", on_budget=True)
    await create_transaction(db_session, budget, checking, "10000.00", TODAY - timedelta(days=40))
    await create_transaction(db_session, budget, loan, "-7000.00", TODAY - timedelta(days=40))

    before_history, before_dashboard = await _net_worth_now(report_svc, budget.id)
    assert before_history == Decimal("3000.00")

    # Creating the Debt entity must not change net worth: the liability is
    # already counted through its account ledger.
    await create_debt(db_session, budget, "Car", linked_account_id=loan.id)

    after_history, after_dashboard = await _net_worth_now(report_svc, budget.id)
    assert after_history == before_history
    assert after_dashboard == before_dashboard
    history = await report_svc.net_worth_history(budget.id, months=3)
    assert history[-1]["unmanaged_debt_total"] == Decimal("0")


async def test_history_before_first_snapshot_shows_no_debt(db_session):
    """A debt tracked starting last month must not rewrite older history."""
    report_svc = ReportService(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    await create_transaction(db_session, budget, checking, "5000.00", TODAY - timedelta(days=200))

    debt = await create_debt(db_session, budget, "Medical", manual_balance=Decimal("900.00"))
    first_snapshot = TODAY.replace(day=1) - timedelta(days=10)  # in the previous month
    await create_debt_snapshot(db_session, debt, first_snapshot, Decimal("900.00"))

    history = await report_svc.net_worth_history(budget.id, months=6)

    oldest = history[0]
    assert oldest["unmanaged_debt_total"] == Decimal("0")
    assert oldest["net_worth"] == Decimal("5000.00")
    assert history[-1]["unmanaged_debt_total"] == Decimal("900.00")
    assert history[-1]["net_worth"] == Decimal("4100.00")
    previous_month = history[-2]
    assert previous_month["unmanaged_debt_total"] == Decimal("900.00")


async def test_api_response_carries_top_level_bucket(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    await create_transaction(db_session, budget, checking, "2000.00", TODAY - timedelta(days=10))
    debt = await create_debt(db_session, budget, "Family", manual_balance=Decimal("450.00"))
    await create_debt_snapshot(db_session, debt, TODAY, Decimal("450.00"))

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/net-worth")
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(str(body["unmanaged_debt_total"])) == Decimal("450.00")
    latest = body["points"][-1]
    assert Decimal(str(latest["net_worth"])) == Decimal("1550.00")
    assert Decimal(str(latest["unmanaged_debt_total"])) == Decimal("450.00")
