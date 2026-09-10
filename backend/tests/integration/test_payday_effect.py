"""Payday effect: average daily spending in the N days after income events.

Pins the cash-flow rules this report must share with every other report:
uncategorized transfer legs are internal money movement — a big transfer
INTO checking is not a payday, and the outflow leg is not spending.
Subscription-tagged payees are excluded from the spending averages (they
fire on their own schedule, not because a payday happened).
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.repositories.payee_repo import PayeeRepository
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
    return budget, checking, group


def _assert_core_expectations(data):
    assert data["event_count"] == 1
    by_offset = {d["offset"]: d["avg_spend"] for d in data["days"]}
    # One payday, so each offset divides by one either way.
    assert by_offset[0] == Decimal("100.00")
    assert by_offset[1] == Decimal("50.00")
    assert by_offset[5] == Decimal("0")
    # `baseline_daily` is "average daily spend outside the window", which is
    # what the schema has always promised — so the 75 spreads across every
    # quiet day in the range rather than dividing by the one day that happened
    # to have spending. The exact figure depends on how many days the range
    # holds, so the arithmetic is pinned in
    # `test_the_baseline_counts_quiet_days_too` rather than hard-coded here.
    assert data["baseline_daily"] is not None
    assert Decimal("0") < data["baseline_daily"] < by_offset[1]


async def test_spending_averages_by_day_after_payday(db_session):
    budget, checking, _group = await _setup_core_scenario(db_session)

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert len(data["days"]) == 14
    _assert_core_expectations(data)


async def test_transfers_are_neither_paydays_nor_spending(db_session):
    budget, checking, _group = await _setup_core_scenario(db_session)
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


async def test_subscription_charges_excluded_from_spending(db_session):
    """A subscription lands on its own schedule whatever the household does
    after being paid, so counting it flattens the effect this report looks for.

    The tag is read from the CATEGORY. This test used to tag a PAYEE, which is
    the only reason the exclusion looked alive: migration b8e5d1c73a49 deleted
    every payee-subscription row and made the routes refuse new ones, so in a
    real budget the reader had been returning an empty set — and excluding
    nothing — since 2026-09-06. The test reached past the guard the product
    enforces, and so kept dead code green.
    """
    budget, checking, group = await _setup_core_scenario(db_session)
    await seed_system_tags(db_session, budget.id)
    tag_repo = TagRepository(db_session)
    sub_tag = await tag_repo.get_system_tag(budget.id, "subscription")
    streaming = await create_category(db_session, budget, group, "Streaming")
    await tag_repo.set_category_tags(streaming.id, [sub_tag.id])
    netflix = await create_payee(db_session, budget, "Northstar Stream")

    # Fires one day after payday, but it is a subscription, not payday behaviour
    await create_transaction(
        db_session,
        budget,
        checking,
        "-15.99",
        TODAY - timedelta(days=19),
        payee=netflix,
        category=streaming,
    )

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    _assert_core_expectations(data)


async def test_an_untagged_charge_at_the_same_payee_still_counts(db_session):
    """The complement, so the exclusion cannot quietly widen to "any payee that
    ever bought a subscription"."""
    budget, checking, group = await _setup_core_scenario(db_session)
    await seed_system_tags(db_session, budget.id)
    shopping = await create_category(db_session, budget, group, "Shopping")
    payee = await create_payee(db_session, budget, "Northstar Stream")
    await create_transaction(
        db_session,
        budget,
        checking,
        "-15.99",
        TODAY - timedelta(days=19),
        payee=payee,
        category=shopping,
    )

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)
    by_offset = {d["offset"]: d["avg_spend"] for d in data["days"]}
    assert by_offset[1] == Decimal("65.99")


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
    await create_transaction(db_session, budget, checking, "-60.00", TODAY - timedelta(days=18))
    # T-11: outside payday 1's window (offsets 0-13), offset 7 of payday 2
    await create_transaction(db_session, budget, checking, "-55.00", TODAY - timedelta(days=11))

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 2
    by_offset = {d["offset"]: d["avg_spend"] for d in data["days"]}
    # Two paydays, and only the second had spending on its own day: (0 + 60)/2.
    # This read 60.00 before, because a payday with nothing spent on an offset
    # day was dropped from that offset's samples rather than counted as a zero
    # — so each bar divided by "paydays that happened to have spending".
    assert by_offset[0] == Decimal("30.00")
    # Offset 7 was hit once per payday and both had spending: (60 + 55) / 2.
    assert by_offset[7] == Decimal("57.50")
    # Every spending day fell inside some window, so every quiet day outside
    # one contributes a zero and the average is zero.
    assert data["baseline_daily"] == Decimal("0")


async def test_no_income_events_returns_zeroed_shape(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    # Inflow below the $200 floor: never an income event
    await create_transaction(db_session, budget, checking, "50.00", TODAY - timedelta(days=10))

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 0
    # None, not 0.00: with no payday there is no "outside a payday window" to
    # average over, and a served 0.00 would claim the household spends nothing.
    assert data["baseline_daily"] is None
    assert all(d["avg_spend"] == Decimal("0") for d in data["days"])


async def test_a_quiet_payday_still_counts_in_the_divisor(db_session):
    """Each bar divides by the number of PAYDAYS, not by the paydays that
    happened to have spending on that day.

    One 300 purchase three days after one of four paydays used to read as a 300
    average for day 3 — and the peak-day ranking inverted whenever a quiet
    payday was dropped from one offset and not another.
    """
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    employer = await create_payee(db_session, budget, "Northwind Payserv")

    # Four paydays, 28 days apart so no two windows overlap.
    for weeks_back in (16, 12, 8, 4):
        await create_transaction(
            db_session,
            budget,
            checking,
            "2000.00",
            TODAY - timedelta(days=weeks_back * 7),
            payee=employer,
        )
    # One splurge, three days after the OLDEST payday only.
    await create_transaction(
        db_session, budget, checking, "-300.00", TODAY - timedelta(days=16 * 7 - 3)
    )

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 4
    by_offset = {d["offset"]: d["avg_spend"] for d in data["days"]}
    # 300 across four paydays, not 300 across the one that spent.
    assert by_offset[3] == Decimal("75.00")


async def test_the_baseline_counts_quiet_days_too(db_session):
    """`baseline_daily` is "average daily spend outside the window", which is
    what the schema promises.

    It collected only days that HAD spending, so it was an average over
    spending days — and those differ from all days by the household's quiet
    ones, which are most of them.
    """
    budget = await create_budget(db_session, await create_user(db_session))
    checking = await create_account(db_session, budget, "Checking")
    employer = await create_payee(db_session, budget, "Northwind Payserv")

    await create_transaction(db_session, budget, checking, "2000.00", TODAY, payee=employer)
    await create_transaction(db_session, budget, checking, "-40.00", TODAY - timedelta(days=2))
    await create_transaction(db_session, budget, checking, "-20.00", TODAY - timedelta(days=4))

    data = await ReportService(db_session).payday_effect(budget.id, window=3, months=12)

    baseline = data["baseline_daily"]
    assert baseline is not None
    # 60 of spending spread over a year of quiet days. An average over the two
    # days that had spending would have given 30.00.
    assert baseline < Decimal("1.00")


async def test_a_payday_savings_sweep_is_not_post_payday_spending(db_session):
    """The outflow side needed the class filter too.

    The method's comment has asserted for months that "the outflow leg of a
    transfer is not spending" with nothing implementing it. Moving money to
    savings the moment it arrives is the loudest thing a disciplined household
    does right after being paid — and the exact opposite of the splurge this
    report looks for, so counting it inverted the finding.
    """
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    brokerage = await create_account(
        db_session, budget, "Cascade Point HYSA", account_type="investment", on_budget=False
    )
    employer = await create_payee(db_session, budget, "Northwind Payserv")
    sweep_payee = await PayeeRepository(db_session).find_or_create_transfer(
        budget.id, brokerage.id, brokerage.name
    )

    await create_transaction(
        db_session, budget, checking, "2000.00", TODAY - timedelta(days=20), payee=employer
    )
    # Same day as the payday: 1,500 swept into the brokerage, 40 of real
    # spending. Only the 40 is spending.
    await create_transaction(
        db_session, budget, checking, "-1500.00", TODAY - timedelta(days=20), payee=sweep_payee
    )
    await create_transaction(db_session, budget, checking, "-40.00", TODAY - timedelta(days=20))

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 1
    by_offset = {d["offset"]: d["avg_spend"] for d in data["days"]}
    assert by_offset[0] == Decimal("40.00")


async def test_a_varying_wage_keeps_every_payday(db_session):
    """The threshold was the P75 of every inflow, so a RELATIVE quartile
    decided which paydays existed — and a quartile of a varying wage discards
    three quarters of them, leaving the report describing the household's
    best-paid weeks only.
    """
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    employer = await create_payee(db_session, budget, "Northwind Payserv")

    # Four paydays of very different size: shift work, or overtime.
    for days_back, amount in ((60, "900.00"), (45, "1400.00"), (30, "2600.00"), (15, "4200.00")):
        await create_transaction(
            db_session, budget, checking, amount, TODAY - timedelta(days=days_back), payee=employer
        )

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    # All four, not just the one above the 75th percentile.
    assert data["event_count"] == 4
