"""Payday effect: the median payday's discretionary spending on each of the N
days after it, against the median day of the whole window.

Pins the cash-flow rules this report must share with every other report:
uncategorized transfer legs are internal money movement — a big transfer
INTO checking is not a payday, and the outflow leg is not spending. Only an
INCOME-class inflow is a payday, so money drawn back from a tracked account
and a large refund are not either. Only discretionary spending counts
(`DISCRETIONARY_ROW`): a bill tagged Cost of living and a subscription both
land on their own schedule, not because a payday happened.

Transfers are built with the SOURCE as `account_id`: `_create_transfer` books
`account_id` as the outflow leg. The first version of these tests had it the
other way round, so "a transfer into checking" never put a cent into checking
and the income-side class filter went unpinned.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_service import PAYDAY_FLOOR, ReportService
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


def _by_offset(data) -> dict[int, Decimal]:
    return {d["offset"]: d["median_spend"] for d in data["days"]}


def _assert_core_expectations(data):
    assert data["event_count"] == 1
    by_offset = _by_offset(data)
    # One payday, so each offset's median is that payday's own day.
    assert by_offset[0] == Decimal("100.00")
    assert by_offset[1] == Decimal("50.00")
    assert by_offset[5] == Decimal("0")
    # The window starts at the first transaction and runs through today, and
    # is served so the page can state it: T-20..T, twenty-one days.
    assert (data["window_start"], data["window_end"]) == (TODAY - timedelta(days=20), TODAY)
    assert data["baseline_days"] == 21
    # Three of those days had spending; the median day had none.
    assert data["baseline_daily"] == Decimal("0.00")


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
    # register a 3000 "spend" on its savings leg. `account_id` is the source.
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=savings.id,
            date=TODAY - timedelta(days=10),
            amount=Decimal("3000.00"),
            transfer_account_id=checking.id,
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
    assert _by_offset(data)[1] == Decimal("65.99")


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
    by_offset = _by_offset(data)
    # Two paydays, and only the second had spending on its own day: the
    # median of (0, 60). This read 60.00 once, because a payday with nothing
    # spent on an offset day was dropped from that offset's samples rather
    # than counted as a zero.
    assert by_offset[0] == Decimal("30.00")
    # Offset 7 was hit once per payday and both had spending: (60, 55).
    assert by_offset[7] == Decimal("57.50")
    # Two spending days in a window of twenty-six: the median day is quiet.
    assert data["baseline_daily"] == Decimal("0")


async def test_no_income_events_returns_zeroed_shape(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    # Inflow below the $200 floor: never an income event
    await create_transaction(db_session, budget, checking, "50.00", TODAY - timedelta(days=10))

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 0
    # None, not 0.00: with no payday there is nothing to compare a baseline
    # with, and the page says so instead of drawing one.
    assert data["baseline_daily"] is None
    assert all(d["median_spend"] == Decimal("0") for d in data["days"])


async def test_a_quiet_payday_is_a_sample_and_one_splurge_is_not_the_typical_day(db_session):
    """Each bar is the median over EVERY payday, the quiet ones included.

    One 300 purchase three days after one of four paydays read as a 300
    average for day 3 while quiet paydays were dropped, then as 75 once they
    counted — a bar four times the household's usual day +3, drawn from one
    purchase. The median payday spent nothing that day, and says so.
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
    (day3,) = [d for d in data["days"] if d["offset"] == 3]
    assert day3["paydays"] == 4
    assert day3["median_spend"] == Decimal("0.00")


async def test_the_median_payday_is_not_the_mean(db_session):
    """Three paydays spending 10, 20 and 900 on the day: the typical payday
    spent 20. The mean, 310, described none of them."""
    budget = await create_budget(db_session, await create_user(db_session))
    checking = await create_account(db_session, budget, "Checking")
    employer = await create_payee(db_session, budget, "Northwind Payserv")
    for back, spend in ((60, "-10.00"), (40, "-20.00"), (20, "-900.00")):
        when = TODAY - timedelta(days=back)
        await create_transaction(db_session, budget, checking, "2000.00", when, payee=employer)
        await create_transaction(db_session, budget, checking, spend, when)

    data = await ReportService(db_session).payday_effect(budget.id, window=7, months=12)

    assert _by_offset(data)[0] == Decimal("20.00")


async def test_the_baseline_counts_quiet_days_too(db_session):
    """`baseline_daily` is the median of EVERY day in the window, what the
    schema promises.

    It once collected only days that HAD spending — a figure over spending
    days, which differ from all days by the household's quiet ones, most of
    them.
    """
    budget = await create_budget(db_session, await create_user(db_session))
    checking = await create_account(db_session, budget, "Checking")
    employer = await create_payee(db_session, budget, "Northwind Payserv")

    await create_transaction(
        db_session, budget, checking, "2000.00", TODAY - timedelta(days=10), payee=employer
    )
    await create_transaction(db_session, budget, checking, "-40.00", TODAY - timedelta(days=5))
    await create_transaction(db_session, budget, checking, "-20.00", TODAY - timedelta(days=3))

    data = await ReportService(db_session).payday_effect(budget.id, window=3, months=12)

    # T-10..T, eleven days, two of them with spending: the median day is
    # quiet. Over the spending days alone it would have read 30.00.
    assert data["baseline_days"] == 11
    assert data["baseline_daily"] == Decimal("0.00")


async def test_a_payday_savings_sweep_is_not_post_payday_spending(db_session):
    """The outflow side needed the class filter too.

    The method's comment has asserted for months that "the outflow leg of a
    transfer is not spending" with nothing implementing it. Moving money to
    savings the moment it arrives is the loudest thing a disciplined household
    does right after being paid — and the exact opposite of the splurge this
    report looks for, so counting it inverted the finding.
    """
    budget = await _payday_with_a_sweep(db_session)

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 1
    assert _by_offset(data)[0] == Decimal("40.00")


async def test_a_bill_is_not_payday_behaviour(db_session):
    """Only discretionary spending counts. The rent lands two days after pay
    whatever the household does, so counting it drew a splurge on day +2
    every month; tagged Cost of living, it is left out, and the dinner out
    beside it stays."""
    budget, checking, group = await _setup_core_scenario(db_session)
    await seed_system_tags(db_session, budget.id)
    tag_repo = TagRepository(db_session)
    committed = await tag_repo.get_system_tag(budget.id, "cost_of_living")
    rent = await create_category(db_session, budget, group, "Rent")
    await tag_repo.set_category_tags(rent.id, [committed.id])
    dining = await create_category(db_session, budget, group, "Dining Out")
    when = TODAY - timedelta(days=18)
    await create_transaction(db_session, budget, checking, "-1400.00", when, category=rent)
    await create_transaction(db_session, budget, checking, "-45.00", when, category=dining)

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert _by_offset(data)[2] == Decimal("45.00")


async def test_a_refund_lowers_its_day(db_session):
    """Net of refunds, like every spending figure: a return five days after
    payday takes that day's discretionary spending below zero."""
    budget, checking, group = await _setup_core_scenario(db_session)
    shopping = await create_category(db_session, budget, group, "Shopping")
    await create_transaction(
        db_session, budget, checking, "60.00", TODAY - timedelta(days=15), category=shopping
    )

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert _by_offset(data)[5] == Decimal("-60.00")


async def _payday_with_a_sweep(db_session):
    """A payday at T-20, with 1,500 swept into an off-budget brokerage and 40
    of real spending the same day."""
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
    return budget


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


async def _flat_register(db_session, *, days_of_history: int, paydays: list[int], daily: str):
    """A register with `daily` spent every day for `days_of_history` days and
    paydays `paydays` days back. Nothing older: a first sync, say."""
    budget = await create_budget(db_session, await create_user(db_session))
    checking = await create_account(db_session, budget, "Checking")
    employer = await create_payee(db_session, budget, "Northwind Payserv")
    for back in paydays:
        await create_transaction(
            db_session, budget, checking, "2000.00", TODAY - timedelta(days=back), payee=employer
        )
    for back in range(days_of_history + 1):
        await create_transaction(
            db_session, budget, checking, f"-{daily}", TODAY - timedelta(days=back)
        )
    return budget


async def test_a_short_history_is_not_a_year_of_quiet_days(db_session):
    """A ninety-day first sync is the common case. The baseline walked every
    day from twelve months back and zero-filled the months before the register
    had any data, so a household spending a flat 50 a day — no payday effect at
    all — was told post-payday spending ran twelve times normal. Nor from the
    first of the first month: those days are not quiet ones either.
    """
    budget = await _flat_register(
        db_session, days_of_history=60, paydays=[56, 42, 28, 14], daily="50.00"
    )

    data = await ReportService(db_session).payday_effect(budget.id, window=7, months=12)

    assert data["event_count"] == 4
    assert data["window_start"] == TODAY - timedelta(days=60)
    assert data["baseline_days"] == 61
    assert data["baseline_daily"] == Decimal("50.00")
    assert all(d["median_spend"] == Decimal("50.00") for d in data["days"])


async def _biweekly_budget(db_session, owner):
    """Biweekly pay up to today, and a spend of 90 five days before the first
    payday in range."""
    budget = await create_budget(db_session, owner)
    checking = await create_account(db_session, budget, "Checking")
    employer = await create_payee(db_session, budget, "Northwind Payserv")
    for back in (42, 28, 14, 0):
        await create_transaction(
            db_session, budget, checking, "2000.00", TODAY - timedelta(days=back), payee=employer
        )
    await create_transaction(db_session, budget, checking, "-90.00", TODAY - timedelta(days=47))
    return budget


async def test_biweekly_pay_at_window_14_still_has_a_baseline(db_session):
    """The baseline averaged only the days outside every payday window, and
    biweekly pay at a 14-day window leaves none: whatever the phase, the page
    had nothing to compare with — or, when the calendar left a few edge days
    before the first payday, a baseline made of those days alone. It is the
    median of every day now, whatever the pay schedule.

    T-47..T is forty-eight days, one of them with spending.
    """
    budget = await _biweekly_budget(db_session, await create_user(db_session))

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 4
    assert data["baseline_days"] == 48
    assert data["baseline_daily"] == Decimal("0.00")


async def test_the_route_serves_the_window_and_the_baseline(api_client, db_session):
    """Through the route: every served figure the page reads."""
    budget = await _biweekly_budget(db_session, api_client.test_user)

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/payday-effect?window=14")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["event_count"] == 4
    assert body["baseline_daily"] == 0.0
    assert body["baseline_days"] == 48
    assert body["window_start"] == (TODAY - timedelta(days=47)).isoformat()
    assert body["window_end"] == TODAY.isoformat()
    assert {"offset", "median_spend", "paydays"} <= set(body["days"][0])
    # The floor the panel quotes is the one the server applied.
    assert body["payday_floor"] == float(PAYDAY_FLOOR)


async def test_exactly_the_floor_is_a_payday_and_a_cent_under_is_not(db_session):
    """The floor alone decides which inflows are paydays, so its edge is the
    rule. 200.00 at T-20 counts; 199.99 at T-10 does not — so T-20 is the only
    payday, and T-10's spend lands on its offset 10."""
    budget = await create_budget(db_session, await create_user(db_session))
    checking = await create_account(db_session, budget, "Checking")
    employer = await create_payee(db_session, budget, "Northwind Payserv")
    for back, amount in ((20, "200.00"), (10, "199.99")):
        await create_transaction(
            db_session, budget, checking, amount, TODAY - timedelta(days=back), payee=employer
        )
    await create_transaction(db_session, budget, checking, "-30.00", TODAY - timedelta(days=20))
    await create_transaction(db_session, budget, checking, "-50.00", TODAY - timedelta(days=10))

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 1
    by_offset = _by_offset(data)
    assert by_offset[0] == Decimal("30.00")
    assert by_offset[10] == Decimal("50.00")


async def test_days_that_have_not_happened_are_not_zeros(db_session):
    """The latest payday's window runs past today. Its future days are skipped,
    not counted as quiet days: zero-filling them would halve every late offset
    here, reading the 80 spent ten days after the older payday as 40."""
    budget = await create_budget(db_session, await create_user(db_session))
    checking = await create_account(db_session, budget, "Checking")
    employer = await create_payee(db_session, budget, "Northwind Payserv")
    for back in (40, 3):
        await create_transaction(
            db_session, budget, checking, "2000.00", TODAY - timedelta(days=back), payee=employer
        )
    await create_transaction(db_session, budget, checking, "-80.00", TODAY - timedelta(days=30))

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 2
    (day10,) = [d for d in data["days"] if d["offset"] == 10]
    # T-30 is offset 10 of T-40; offset 10 of T-3 is a week from now.
    assert day10["paydays"] == 1
    assert day10["median_spend"] == Decimal("80.00")


async def test_only_income_is_a_payday(db_session):
    """The income side's class filter, pinned. Under the absolute floor it is
    the only thing keeping these two inflows — both over 200 — from being
    paydays: money drawn back from a tracked savings account, and a refund
    filed to a spending category."""
    budget, checking, group = await _setup_core_scenario(db_session)
    services = make_services(db_session)
    hysa = await create_account(
        db_session, budget, "Cascade Point HYSA", account_type="investment", on_budget=False
    )
    household = await create_category(db_session, budget, group, "Household")

    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=hysa.id,
            date=TODAY - timedelta(days=12),
            amount=Decimal("500.00"),
            transfer_account_id=checking.id,
            cleared="cleared",
        ),
    )
    await create_transaction(
        db_session, budget, checking, "250.00", TODAY - timedelta(days=15), category=household
    )

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    assert data["event_count"] == 1
    by_offset = _by_offset(data)
    assert (by_offset[0], by_offset[1]) == (Decimal("100.00"), Decimal("50.00"))
    # Not a payday — but a refund to a spending category, so it lowers the
    # day it landed on (offset 5 of T-20), net of refunds like every figure.
    assert by_offset[5] == Decimal("-250.00")


async def test_a_credit_on_a_card_is_never_a_payday(db_session):
    """A card bill paid from checking whose two legs were never linked arrives
    on the card as a plain credit — the unlinked-payment card scenario. It has
    no category, so it classes INCOME, and at 300 it clears the floor: every
    month the bill was paid read as a second payday. A wage lands in cash."""
    budget, checking, _group = await _setup_core_scenario(db_session)
    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    await create_transaction(db_session, budget, card, "300.00", TODAY - timedelta(days=12))

    data = await ReportService(db_session).payday_effect(budget.id, window=14, months=12)

    _assert_core_expectations(data)
