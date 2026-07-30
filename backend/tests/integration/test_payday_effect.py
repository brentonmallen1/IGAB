"""Payday effect: average daily spending in the N days after income events.

Pins the cash-flow rules this report must share with every other report:
uncategorized transfer legs are internal money movement — a big transfer
INTO checking is not a payday, and the outflow leg is not spending.
Subscription-tagged payees are excluded from the spending averages (they
fire on their own schedule, not because a payday happened).
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_service import ReportService
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

TODAY = date.today()


async def _setup_core_scenario(db_session):
    """Salary at T-20; spends of 100/50 on days 0/1 after; 75 outside the window."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")

    employer = await create_payee(db_session, budget, "Employer")
    await create_transaction(
        db_session, budget, checking, "2000.00", TODAY - timedelta(days=20), payee=employer
    )
    await create_transaction(
        db_session, budget, checking, "-100.00", TODAY - timedelta(days=20), category=groceries
    )
    await create_transaction(
        db_session, budget, checking, "-50.00", TODAY - timedelta(days=19), category=groceries
    )
    # Outside the 14-day window: baseline spending
    await create_transaction(
        db_session, budget, checking, "-75.00", TODAY - timedelta(days=5), category=groceries
    )
    return budget, checking


def _assert_core_expectations(data):
    assert data["event_count"] == 1
    by_offset = {d["offset"]: d["avg_spend"] for d in data["days"]}
    assert by_offset[0] == Decimal("100.00")
    assert by_offset[1] == Decimal("50.00")
    # Days with no spending contribute nothing — they read as zero
    assert by_offset[5] == Decimal("0")
    assert data["baseline_daily"] == Decimal("75.00")


async def test_spending_averages_by_day_after_payday(db_session):
    budget, checking = await _setup_core_scenario(db_session)

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert len(data["days"]) == 14
    _assert_core_expectations(data)


async def test_transfers_are_neither_paydays_nor_spending(db_session):
    budget, checking = await _setup_core_scenario(db_session)
    services = make_services(db_session)
    savings = await create_account(db_session, budget, "Savings")

    # A 3000 transfer into checking: bigger than the salary, but internal.
    # If counted, it would both displace the salary as the income event and
    # register a 3000 "spend" on its savings leg.
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY - timedelta(days=10),
            amount=Decimal("3000.00"),
            transfer_account_id=savings.id,
            cleared="cleared",
        ),
    )

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    # Identical to the transfer-free scenario
    _assert_core_expectations(data)


async def test_subscription_payees_excluded_from_spending(db_session):
    budget, checking = await _setup_core_scenario(db_session)
    await seed_system_tags(db_session, budget.id)
    tag_repo = TagRepository(db_session)
    sub_tag = await tag_repo.get_system_tag(budget.id, "subscription")
    netflix = await create_payee(db_session, budget, "Netflix")
    await tag_repo.add_payee_tag(netflix.id, sub_tag.id)

    # Fires one day after payday, but it's a subscription, not payday behavior
    await create_transaction(
        db_session, budget, checking, "-15.99", TODAY - timedelta(days=19), payee=netflix
    )

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    _assert_core_expectations(data)


async def test_overlapping_paydays_share_offset_days(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    employer = await create_payee(db_session, budget, "Employer")

    # Two paydays 7 days apart: their 14-day windows overlap
    await create_transaction(
        db_session, budget, checking, "2000.00", TODAY - timedelta(days=25), payee=employer
    )
    await create_transaction(
        db_session, budget, checking, "2000.00", TODAY - timedelta(days=18), payee=employer
    )
    # T-18: offset 7 of payday 1 AND offset 0 of payday 2
    await create_transaction(
        db_session, budget, checking, "-60.00", TODAY - timedelta(days=18)
    )
    # T-11: outside payday 1's window (offsets 0-13), offset 7 of payday 2
    await create_transaction(
        db_session, budget, checking, "-55.00", TODAY - timedelta(days=11)
    )

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 2
    by_offset = {d["offset"]: d["avg_spend"] for d in data["days"]}
    assert by_offset[0] == Decimal("60.00")
    # Offset 7 was hit once per payday: (60 + 55) / 2
    assert by_offset[7] == Decimal("57.50")
    # Every spending day fell inside some window — nothing left for baseline
    assert data["baseline_daily"] == Decimal("0")


async def test_no_income_events_returns_zeroed_shape(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    # Inflow below the $200 floor: never an income event
    await create_transaction(
        db_session, budget, checking, "50.00", TODAY - timedelta(days=10)
    )

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 0
    assert data["baseline_daily"] == Decimal("0")
    assert all(d["avg_spend"] == Decimal("0") for d in data["days"])
