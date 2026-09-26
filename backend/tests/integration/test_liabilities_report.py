"""Consolidated liabilities report: rollup totals, filters, and the balance series."""

from datetime import date, timedelta
from decimal import Decimal

from igab.domain.dates import add_months
from igab.repositories.liability_repo import LiabilityRepository
from igab.services.liability_service import LiabilityService
from igab.services.report_service import ReportService

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

    # The divergence the note states, pinned: net worth still counts the
    # closed debt, by exactly the amount the note names (PR190-14). A change
    # that drops closed accounts from net worth leaves the page saying "but
    # net worth still counts it" about a figure that no longer does.
    net_worth = (await ReportService(db_session).net_worth_history(budget.id, months=1))[-1]
    assert net_worth["total_liabilities"] == (
        report["total_balance"] + report["closed_with_balance_total"]
    )


async def _with_a_closed_auto_loan_owing(db_session):
    services, budget, _managed, _unmanaged = await _setup(db_session)
    settled = await create_account(
        db_session, budget, "Old Auto Loan", account_type="auto_loan", on_budget=False
    )
    await create_transaction(db_session, budget, settled, "-3000.00", TODAY - timedelta(days=200))
    await create_liability(
        db_session, budget, "Trade-in", liability_type="auto", linked_account_id=settled.id
    )
    settled.is_closed = True
    await db_session.flush()
    return make_liability_service(db_session, services), budget


async def test_a_filter_that_excludes_the_closed_loan_says_nothing_of_it(db_session):
    """The note counted the closed debt budget-wide while the total beside it
    was filtered, so the Personal pill read "$1,200 of personal debt" above a
    note that $3,000 on a closed auto loan was left out of it (PR190-5)."""
    svc, budget = await _with_a_closed_auto_loan_owing(db_session)

    personal = await svc.liabilities_report(budget.id, liability_type="personal")
    assert personal["total_balance"] == Decimal("1200.00")
    assert personal["closed_with_balance_count"] == 0
    assert personal["closed_with_balance_total"] == Decimal("0")

    # Unmanaged: the closed loan is managed (it reads its account's ledger).
    unmanaged = await svc.liabilities_report(budget.id, mode="unmanaged")
    assert unmanaged["closed_with_balance_count"] == 0


async def test_a_filter_that_includes_the_closed_loan_still_names_it(db_session):
    svc, budget = await _with_a_closed_auto_loan_owing(db_session)

    auto = await svc.liabilities_report(budget.id, liability_type="auto_loan")
    assert [i["name"] for i in auto["items"]] == ["Car"]
    assert auto["closed_with_balance_count"] == 1
    assert auto["closed_with_balance_total"] == Decimal("3000.00")

    managed = await svc.liabilities_report(budget.id, mode="managed")
    assert managed["closed_with_balance_count"] == 1


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


# ─── A debt that never pays off ──────────────────────────────────────────────


async def _three_debts(db_session):
    """Three stated debts with no payment history, so the minimum speaks for
    each: one it never touches, one it barely covers, one it clears.

    - Sapphire Visa: $10,000 at 24% — $200.00 of interest a month — on a
      $100.00 minimum. Never.
    - Harborstone Mortgage: $100,000 at 6% — $500.00 a month — on $500.01.
      A cent of principal a month: the 600-month cap ends it, never paid.
    - Jane Doe Loan: $1,000 at 12% on $400.00. Three payments and $18.26
      of interest (`test_amortization.TestHandComputedSchedule`).
    """
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    for name, balance, rate, minimum in (
        ("Sapphire Visa", "10000.00", "24", "100.00"),
        ("Harborstone Mortgage", "100000.00", "6", "500.01"),
        ("Jane Doe Loan", "1000.00", "12", "400.00"),
    ):
        await create_liability(
            db_session,
            budget,
            name,
            manual_balance=Decimal(balance),
            interest_rate=Decimal(rate),
            minimum_payment=Decimal(minimum),
        )
    return make_liability_service(db_session, services), budget


async def test_a_debt_the_minimum_never_pays_off_has_no_interest_bill(db_session):
    """It read "Interest left $0.00" and added $0 to Interest Remaining; the
    barely-covered one added fifty years of interest instead. Neither is what
    is left, and `project_payoff` already said so for the observed pace."""
    svc, budget = await _three_debts(db_session)

    report = await svc.liabilities_report(budget.id, as_of=TODAY)
    by_name = {i["name"]: i for i in report["items"]}

    for never in ("Sapphire Visa", "Harborstone Mortgage"):
        item = by_name[never]
        assert item["total_interest_remaining"] is None, never
        assert item["baseline_payoff_date"] is None
        assert item["baseline_never_pays_off"] is True
        assert item["never_pays_off"] is True
        assert item["terms_complete"] is True

    cleared = by_name["Jane Doe Loan"]
    assert cleared["total_interest_remaining"] == Decimal("18.26")
    assert cleared["baseline_never_pays_off"] is False
    assert cleared["never_pays_off"] is False

    # The headline is the one finite bill, and says what it left out.
    assert report["total_interest_remaining"] == Decimal("18.26")
    assert report["liabilities_never_paying_off"] == 2
    assert report["liabilities_missing_terms"] == 0


async def test_without_payment_history_the_verdict_is_the_minimums(db_session):
    """No payments on record, so there is no pace: the verdict is the
    minimum's, and the page must not call it "current pace"."""
    svc, budget = await _three_debts(db_session)

    report = await svc.liabilities_report(budget.id, as_of=TODAY)

    assert {i["name"]: i["payoff_basis"] for i in report["items"]} == {
        "Sapphire Visa": "minimum",
        "Harborstone Mortgage": "minimum",
        "Jane Doe Loan": "minimum",
    }


async def test_with_a_pace_the_verdict_is_the_pace_and_the_interest_the_minimums(db_session):
    """Two months of $100 drops on a $10,000 card at 24%: the pace never
    covers the $200 of monthly interest, while its $300 minimum would. The
    verdict is the pace's ("at current pace" is true here); the interest,
    like the headline it adds into, is the minimum's — finite."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    card = await create_liability(
        db_session,
        budget,
        "Sapphire Visa",
        manual_balance=Decimal("10000.00"),
        interest_rate=Decimal("24"),
        minimum_payment=Decimal("300.00"),
    )
    this_month = TODAY.replace(day=1)
    for months_back, balance in ((3, "10200.00"), (2, "10100.00"), (1, "10000.00")):
        await create_liability_snapshot(
            db_session, card, add_months(this_month, -months_back), Decimal(balance)
        )
    svc = make_liability_service(db_session, services)

    (item,) = (await svc.liabilities_report(budget.id, as_of=TODAY))["items"]

    assert item["payoff_basis"] == "observed"
    assert item["never_pays_off"] is True
    assert item["live_payoff_date"] is None
    assert item["baseline_never_pays_off"] is False
    assert item["baseline_payoff_date"] is not None
    assert item["total_interest_remaining"] is not None
    assert item["total_interest_remaining"] > Decimal("0")


async def test_no_terms_is_no_verdict(db_session):
    """Unknown is not "never", and it is not a basis either."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await create_liability(
        db_session,
        budget,
        "Jane Doe Loan",
        manual_balance=Decimal("500.00"),
        interest_rate=None,
        minimum_payment=None,
    )
    svc = make_liability_service(db_session, services)

    report = await svc.liabilities_report(budget.id, as_of=TODAY)
    (item,) = report["items"]

    assert item["payoff_basis"] is None
    assert item["never_pays_off"] is False
    assert item["baseline_never_pays_off"] is False
    assert item["total_interest_remaining"] is None
    assert report["liabilities_missing_terms"] == 1
    assert report["liabilities_never_paying_off"] == 0


async def test_the_served_report_carries_the_count_and_the_basis(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    await create_liability(
        db_session,
        budget,
        "Sapphire Visa",
        manual_balance=Decimal("10000.00"),
        interest_rate=Decimal("24"),
        minimum_payment=Decimal("100.00"),
    )

    resp = await api_client.get(
        f"/api/v1/{budget.id}/reports/liabilities", params={"client_today": TODAY.isoformat()}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    (item,) = body["items"]
    assert item["total_interest_remaining"] is None
    assert item["payoff_basis"] == "minimum"
    assert item["baseline_never_pays_off"] is True
    assert body["liabilities_never_paying_off"] == 1
    assert Decimal(str(body["total_interest_remaining"])) == Decimal("0")
