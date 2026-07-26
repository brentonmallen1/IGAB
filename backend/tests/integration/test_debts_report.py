"""Consolidated debts report: rollup totals, filters, and the balance series."""

from datetime import date, timedelta
from decimal import Decimal

from igab.repositories.debt_repo import DebtRepository
from igab.services.debt_service import DebtService

from .factories import (
    create_account,
    create_budget,
    create_debt,
    create_debt_snapshot,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()


def make_debt_service(db_session, services) -> DebtService:
    return DebtService(
        DebtRepository(db_session),
        services.account_repo,
        services.category_repo,
        services.transaction_repo,
    )


async def _setup(db_session):
    """One managed auto loan (7000) + one unmanaged personal debt (1200)."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    loan = await create_account(db_session, budget, "Car Loan", account_type="loan", on_budget=False)
    await create_transaction(db_session, budget, loan, "-7000.00", TODAY - timedelta(days=90))
    managed = await create_debt(
        db_session, budget, "Car", debt_type="auto", linked_account_id=loan.id
    )
    unmanaged = await create_debt(
        db_session, budget, "Family", debt_type="personal", manual_balance=Decimal("1200.00")
    )
    await create_debt_snapshot(db_session, unmanaged, TODAY - timedelta(days=60), Decimal("1400.00"))
    await create_debt_snapshot(db_session, unmanaged, TODAY, Decimal("1200.00"))
    return services, budget, managed, unmanaged


async def test_rollup_totals_equal_sum_of_debts(db_session):
    services, budget, managed, unmanaged = await _setup(db_session)
    svc = make_debt_service(db_session, services)

    report = await svc.debts_report(budget.id)

    assert len(report["items"]) == 2
    by_name = {i["name"]: i for i in report["items"]}
    assert by_name["Car"]["current_balance"] == Decimal("7000.00")
    assert by_name["Car"]["mode"] == "managed"
    assert by_name["Family"]["current_balance"] == Decimal("1200.00")
    assert by_name["Family"]["mode"] == "unmanaged"
    assert report["total_balance"] == Decimal("8200.00")
    assert report["total_interest_remaining"] == sum(
        (i["total_interest_remaining"] for i in report["items"]), Decimal("0")
    )


async def test_balance_over_time_totals_are_consistent(db_session):
    services, budget, *_ = await _setup(db_session)
    svc = make_debt_service(db_session, services)

    report = await svc.debts_report(budget.id)
    points = report["balance_over_time"]

    assert points, "series must exist when debts have history"
    for point in points:
        assert point["total"] == sum(point["per_debt"].values(), Decimal("0"))
    # The latest point carries the live totals
    assert points[-1]["total"] == Decimal("8200.00")


async def test_filters_narrow_items_and_totals(db_session):
    services, budget, *_ = await _setup(db_session)
    svc = make_debt_service(db_session, services)

    by_type = await svc.debts_report(budget.id, debt_type="auto")
    assert [i["name"] for i in by_type["items"]] == ["Car"]
    assert by_type["total_balance"] == Decimal("7000.00")

    by_mode = await svc.debts_report(budget.id, mode="unmanaged")
    assert [i["name"] for i in by_mode["items"]] == ["Family"]
    assert by_mode["total_balance"] == Decimal("1200.00")
    # Series only includes the filtered debts
    assert by_mode["balance_over_time"][-1]["total"] == Decimal("1200.00")


async def test_zero_debts_is_a_clean_empty_payload(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/debts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert Decimal(str(body["total_balance"])) == Decimal("0")
    assert body["balance_over_time"] == []


async def test_api_endpoint_with_filters(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    await create_debt(
        db_session, budget, "Family", debt_type="personal", manual_balance=Decimal("500.00")
    )
    await create_debt(
        db_session, budget, "Hospital", debt_type="medical", manual_balance=Decimal("300.00")
    )

    all_debts = await api_client.get(f"/api/v1/{budget.id}/reports/debts")
    assert len(all_debts.json()["items"]) == 2
    assert Decimal(str(all_debts.json()["total_balance"])) == Decimal("800.00")

    medical = await api_client.get(
        f"/api/v1/{budget.id}/reports/debts", params={"debt_type": "medical"}
    )
    body = medical.json()
    assert [i["name"] for i in body["items"]] == ["Hospital"]
    assert Decimal(str(body["total_balance"])) == Decimal("300.00")
