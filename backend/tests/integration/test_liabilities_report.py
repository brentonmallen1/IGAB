"""Consolidated liabilities report: rollup totals, filters, and the balance series."""

from datetime import date, timedelta
from decimal import Decimal

from igab.repositories.liability_repo import LiabilityRepository
from igab.services.liability_service import LiabilityService

from .factories import (
    create_account,
    create_budget,
    create_liability,
    create_liability_snapshot,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()


def make_liability_service(db_session, services) -> LiabilityService:
    return LiabilityService(
        LiabilityRepository(db_session),
        services.account_repo,
        services.category_repo,
        services.transaction_repo,
    )


async def _setup(db_session):
    """One managed auto loan (7000) + one unmanaged personal liability (1200)."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    loan = await create_account(
        db_session, budget, "Car Loan", account_type="auto_loan", on_budget=False
    )
    await create_transaction(db_session, budget, loan, "-7000.00", TODAY - timedelta(days=90))
    managed = await create_liability(
        db_session, budget, "Car", liability_type="auto", linked_account_id=loan.id
    )
    unmanaged = await create_liability(
        db_session, budget, "Family", liability_type="personal", manual_balance=Decimal("1200.00")
    )
    await create_liability_snapshot(
        db_session, unmanaged, TODAY - timedelta(days=60), Decimal("1400.00")
    )
    await create_liability_snapshot(db_session, unmanaged, TODAY, Decimal("1200.00"))
    return services, budget, managed, unmanaged


async def test_rollup_totals_equal_sum_of_liabilities(db_session):
    services, budget, managed, unmanaged = await _setup(db_session)
    svc = make_liability_service(db_session, services)

    report = await svc.liabilities_report(budget.id)

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
    svc = make_liability_service(db_session, services)

    report = await svc.liabilities_report(budget.id)
    points = report["balance_over_time"]

    assert points, "series must exist when liabilities have history"
    for point in points:
        assert point["total"] == sum(point["per_liability"].values(), Decimal("0"))
    # The latest point carries the live totals
    assert points[-1]["total"] == Decimal("8200.00")


async def test_filters_narrow_items_and_totals(db_session):
    services, budget, *_ = await _setup(db_session)
    svc = make_liability_service(db_session, services)

    # The filter matches what the report SHOWS. A managed liability's kind is
    # its account's type now, so "auto_loan" is the value on screen — filtering
    # the stored column would hide a row whose visible type matches.
    by_type = await svc.liabilities_report(budget.id, liability_type="auto_loan")
    assert [i["name"] for i in by_type["items"]] == ["Car"]
    assert by_type["total_balance"] == Decimal("7000.00")

    by_mode = await svc.liabilities_report(budget.id, mode="unmanaged")
    assert [i["name"] for i in by_mode["items"]] == ["Family"]
    assert by_mode["total_balance"] == Decimal("1200.00")
    # Series only includes the filtered liabilities
    assert by_mode["balance_over_time"][-1]["total"] == Decimal("1200.00")


async def test_zero_liabilities_is_a_clean_empty_payload(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/liabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert Decimal(str(body["total_balance"])) == Decimal("0")
    assert body["balance_over_time"] == []


async def test_api_endpoint_with_filters(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    await create_liability(
        db_session, budget, "Family", liability_type="personal", manual_balance=Decimal("500.00")
    )
    await create_liability(
        db_session, budget, "Hospital", liability_type="medical", manual_balance=Decimal("300.00")
    )

    all_liabilities = await api_client.get(f"/api/v1/{budget.id}/reports/liabilities")
    assert len(all_liabilities.json()["items"]) == 2
    assert Decimal(str(all_liabilities.json()["total_balance"])) == Decimal("800.00")

    medical = await api_client.get(
        f"/api/v1/{budget.id}/reports/liabilities", params={"liability_type": "medical"}
    )
    body = medical.json()
    assert [i["name"] for i in body["items"]] == ["Hospital"]
    assert Decimal(str(body["total_balance"])) == Decimal("300.00")


async def test_a_closed_account_still_owing_is_counted_out_loud(db_session):
    """`get_all` drops a loan under a CLOSED account — right for every reader
    asking "what do I still owe", and resting on an assumption nobody stated:
    that closing an account means the debt is gone.

    Close one with a balance still on it and net worth keeps counting it (it
    filters only `is_deleted`) while this report does not, so two figures
    labelled Total Liabilities disagreed with nothing on the page saying why.
    The exclusion stays; the report says what it left out.
    """
    services, budget, _managed, _unmanaged = await _setup(db_session)
    svc = make_liability_service(db_session, services)

    settled = await create_account(
        db_session, budget, "Old Auto Loan", account_type="auto_loan", on_budget=False
    )
    await create_transaction(db_session, budget, settled, "-3000.00", TODAY - timedelta(days=200))
    await create_liability(
        db_session, budget, "Trade-in", liability_type="auto", linked_account_id=settled.id
    )
    settled.is_closed = True
    await db_session.flush()

    report = await svc.liabilities_report(budget.id)

    # Still excluded from the list and from the total.
    assert sorted(i["name"] for i in report["items"]) == ["Car", "Family"]
    assert report["total_balance"] == Decimal("8200.00")
    # And now said out loud. Read through `get_balance`, not `manual_balance`:
    # a managed loan carries no manual figure at all.
    assert report["closed_with_balance_count"] == 1
    assert report["closed_with_balance_total"] == Decimal("3000.00")


async def test_a_closed_account_that_was_paid_off_says_nothing(db_session):
    """The note is for a debt that outlived its account, not for every closed
    one — a settled loan is exactly what the exclusion is for."""
    services, budget, _managed, _unmanaged = await _setup(db_session)
    svc = make_liability_service(db_session, services)

    paid = await create_account(
        db_session, budget, "Paid Auto Loan", account_type="auto_loan", on_budget=False
    )
    await create_transaction(db_session, budget, paid, "-5000.00", TODAY - timedelta(days=400))
    await create_transaction(db_session, budget, paid, "5000.00", TODAY - timedelta(days=30))
    await create_liability(
        db_session, budget, "Settled", liability_type="auto", linked_account_id=paid.id
    )
    paid.is_closed = True
    await db_session.flush()

    report = await svc.liabilities_report(budget.id)
    assert report["closed_with_balance_count"] == 0
    assert report["closed_with_balance_total"] == Decimal("0")
