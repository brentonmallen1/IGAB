"""Cash projection: fan chart over on-budget cash.

The simulation is seeded from today's ordinal, so results are deterministic
within a day. Two engineered scenarios make every band collapse onto a known
path (no history -> all sampled flows are 0; uniform history -> every sample
is identical), which lets exact balances be asserted. Random-history tests
assert only structural invariants (band ordering, same-day idempotence).

Also pins the scope rule: the projection is ON-BUDGET cash, so off-budget
and closed accounts contribute neither balance, nor sampled history, nor
scheduled events — and pending transactions contribute nothing anywhere.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_payee,
    create_scheduled_transaction,
    create_transaction,
    create_user,
)

TODAY = date.today()


async def _budget_with_checking(db_session, opening: str = "5000.00"):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    # Opening balance 200 days back: counts toward the balance but sits
    # outside the 180-day history window, keeping sampled flows empty.
    await create_transaction(
        db_session, budget, checking, opening, TODAY - timedelta(days=200)
    )
    return budget, checking


def _assert_bands_collapsed(points):
    for p in points:
        assert p["p10"] == p["p25"] == p["p50"] == p["p75"] == p["p90"]


async def test_scheduled_transactions_drive_a_deterministic_path(db_session):
    budget, checking = await _budget_with_checking(db_session)
    rent_payee = await create_payee(db_session, budget, "Landlord")
    pay_payee = await create_payee(db_session, budget, "Employer")
    await create_scheduled_transaction(
        db_session, budget, checking, "-1200.00", "monthly",
        TODAY + timedelta(days=10), payee=rent_payee,
    )
    await create_scheduled_transaction(
        db_session, budget, checking, "2000.00", "biweekly",
        TODAY + timedelta(days=3), payee=pay_payee,
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)

    assert data["start_balance"] == Decimal("5000.00")
    points = data["points"]
    assert len(points) == 31
    assert [p["date"] for p in points] == [TODAY + timedelta(days=k) for k in range(31)]
    # No sampled history -> every simulated path equals the deterministic one
    _assert_bands_collapsed(points)
    for p in points:
        assert p["p50"] == p["deterministic"]
    assert points[0]["deterministic"] == Decimal("5000.00")
    assert points[3]["deterministic"] == Decimal("7000.00")  # +2000 paycheck
    assert points[10]["deterministic"] == Decimal("5800.00")  # -1200 rent
    assert points[17]["deterministic"] == Decimal("7800.00")  # +2000 paycheck
    assert points[30]["deterministic"] == Decimal("7800.00")
    assert data["goes_negative_date"] is None

    assert [(e["date"], e["amount"], e["source"]) for e in data["events"]] == [
        (TODAY + timedelta(days=3), Decimal("2000.00"), "scheduled"),
        (TODAY + timedelta(days=10), Decimal("-1200.00"), "scheduled"),
        (TODAY + timedelta(days=17), Decimal("2000.00"), "scheduled"),
    ]


async def test_uniform_history_projects_constant_daily_flow(db_session):
    budget, checking = await _budget_with_checking(db_session, opening="310.00")
    # 21 consecutive days of exactly -10: every weekday bucket holds only -10,
    # so every sampled flow is -10 and all 500 paths are identical.
    for days_back in range(1, 22):
        await create_transaction(
            db_session, budget, checking, "-10.00", TODAY - timedelta(days=days_back)
        )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)

    assert data["start_balance"] == Decimal("100.00")  # 310 - 21 * 10
    points = data["points"]
    _assert_bands_collapsed(points)
    for k, p in enumerate(points):
        assert p["p50"] == Decimal(100 - 10 * (k + 1))
    # Median crosses zero on day 10 (100 - 10*11 = -10)
    assert data["goes_negative_date"] == TODAY + timedelta(days=10)


async def test_off_budget_closed_pending_and_deleted_contribute_nothing(db_session):
    budget, checking = await _budget_with_checking(db_session)

    # Each of these would distort the projection if it leaked in:
    tracking = await create_account(db_session, budget, "Brokerage", on_budget=False)
    await create_transaction(
        db_session, budget, tracking, "9999.00", TODAY - timedelta(days=50)
    )
    closed = await create_account(db_session, budget, "Old Checking")
    await create_transaction(db_session, budget, closed, "777.00", TODAY - timedelta(days=40))
    closed.is_closed = True
    await db_session.flush()
    await create_transaction(
        db_session, budget, checking, "500.00", TODAY - timedelta(days=5), cleared="pending"
    )
    await create_scheduled_transaction(
        db_session, budget, tracking, "-999.00", "monthly", TODAY + timedelta(days=5)
    )
    await create_scheduled_transaction(
        db_session, budget, checking, "-111.00", "monthly", TODAY + timedelta(days=3),
        is_deleted=True,
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=20)

    assert data["start_balance"] == Decimal("5000.00")
    _assert_bands_collapsed(data["points"])
    for p in data["points"]:
        assert p["p50"] == p["deterministic"] == Decimal("5000.00")
    assert data["events"] == []


async def test_subscription_charges_project_monthly_from_last_charge(db_session):
    budget, checking = await _budget_with_checking(db_session)
    await seed_system_tags(db_session, budget.id)
    tag_repo = TagRepository(db_session)
    sub_tag = await tag_repo.get_system_tag(budget.id, "subscription")
    netflix = await create_payee(db_session, budget, "Netflix")
    await tag_repo.add_payee_tag(netflix.id, sub_tag.id)

    await create_transaction(
        db_session, budget, checking, "-15.99", TODAY - timedelta(days=55), payee=netflix
    )
    await create_transaction(
        db_session, budget, checking, "-15.99", TODAY - timedelta(days=25), payee=netflix
    )
    # A pending auth must shift neither the typical amount nor the cadence
    await create_transaction(
        db_session, budget, checking, "-99.00", TODAY - timedelta(days=10),
        payee=netflix, cleared="pending",
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)

    # Last real charge 25 days ago + 30-day cadence -> next charge in 5 days
    assert [(e["date"], e["amount"], e["source"]) for e in data["events"]] == [
        (TODAY + timedelta(days=5), Decimal("-15.99"), "subscription"),
    ]
    start = data["start_balance"]
    assert start == Decimal("4968.02")  # 5000 - two posted charges
    assert data["points"][5]["deterministic"] == start - Decimal("15.99")


async def test_scheduled_end_date_and_event_cap_respected(db_session):
    budget, checking = await _budget_with_checking(db_session)
    await create_scheduled_transaction(
        db_session, budget, checking, "-5.00", "weekly",
        TODAY + timedelta(days=2), end_date=TODAY + timedelta(days=9),
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)
    assert [e["date"] for e in data["events"]] == [
        TODAY + timedelta(days=2),
        TODAY + timedelta(days=9),
    ]

    # A daily schedule floods the 30-day event window; the list caps at 20
    budget2, checking2 = await _budget_with_checking(db_session)
    await create_scheduled_transaction(
        db_session, budget2, checking2, "-1.00", "daily", TODAY
    )
    data2 = await ReportService(db_session).cash_projection(budget2.id, horizon_days=90)
    assert len(data2["events"]) == 20


async def test_percentile_bands_ordered_and_same_day_idempotent(db_session):
    budget, checking = await _budget_with_checking(db_session)
    amounts = ["-20", "500", "-35", "-80", "250", "-15", "-60", "-45", "100", "-25", "-70", "-90"]
    for i, amount in enumerate(amounts):
        await create_transaction(
            db_session, budget, checking, amount, TODAY - timedelta(days=3 * i + 1)
        )
    await create_scheduled_transaction(
        db_session, budget, checking, "-100.00", "monthly", TODAY + timedelta(days=7)
    )

    reports = ReportService(db_session)
    first = await reports.cash_projection(budget.id, horizon_days=45)
    second = await reports.cash_projection(budget.id, horizon_days=45)

    for p in first["points"]:
        assert p["p10"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p90"]
    assert first == second
