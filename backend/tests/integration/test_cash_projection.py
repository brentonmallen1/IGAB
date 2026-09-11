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

from igab.domain.dates import add_months, month_end
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_scheduled_transaction,
    create_transaction,
    create_user,
)

# Cards are ON-budget, which is why they need their own test below: the
# off-budget scope test cannot catch a card leaking in.

TODAY = date.today()


async def _budget_with_checking(db_session, opening: str = "5000.00"):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    # Opening balance 200 days back: counts toward the balance but sits
    # outside the 180-day history window, keeping sampled flows empty.
    await create_transaction(db_session, budget, checking, opening, TODAY - timedelta(days=200))
    return budget, checking


def _assert_bands_collapsed(points):
    for p in points:
        assert p["p10"] == p["p25"] == p["p50"] == p["p75"] == p["p90"]


def _charged_dates(points) -> list[date]:
    """Days the deterministic path moves: the fixed events' dates, read off
    the path rather than recomputed with the stepping under test."""
    return [
        p["date"]
        for i, p in enumerate(points)
        if i > 0 and p["deterministic"] != points[i - 1]["deterministic"]
    ]


def _assert_sampled_flow_per_day(points, per_day: Decimal):
    """Every path carries exactly `per_day` of sampled flow on top of the fixed
    events — what uniform history leaves in the bootstrap."""
    _assert_bands_collapsed(points)
    for k, p in enumerate(points):
        assert p["p50"] - p["deterministic"] == per_day * (k + 1)


async def _subscription_category(db_session, budget, name: str):
    await seed_system_tags(db_session, budget.id)
    tag_repo = TagRepository(db_session)
    sub_tag = await tag_repo.get_system_tag(budget.id, "subscription")
    group = await create_category_group(db_session, budget, "Everyday")
    category = await create_category(db_session, budget, group, name)
    await tag_repo.set_category_tags(category.id, [sub_tag.id])
    return category


async def test_scheduled_transactions_drive_a_deterministic_path(db_session):
    budget, checking = await _budget_with_checking(db_session)
    rent_payee = await create_payee(db_session, budget, "Landlord")
    pay_payee = await create_payee(db_session, budget, "Employer")
    await create_scheduled_transaction(
        db_session,
        budget,
        checking,
        "-1200.00",
        "monthly",
        TODAY + timedelta(days=10),
        payee=rent_payee,
    )
    await create_scheduled_transaction(
        db_session,
        budget,
        checking,
        "2000.00",
        "biweekly",
        TODAY + timedelta(days=3),
        payee=pay_payee,
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


async def test_off_budget_pending_and_deleted_contribute_nothing(db_session):
    budget, checking = await _budget_with_checking(db_session)

    # Each of these would distort the projection if it leaked in:
    tracking = await create_account(db_session, budget, "Brokerage", on_budget=False)
    await create_transaction(db_session, budget, tracking, "9999.00", TODAY - timedelta(days=50))
    await create_transaction(
        db_session, budget, checking, "500.00", TODAY - timedelta(days=5), cleared="pending"
    )
    await create_scheduled_transaction(
        db_session, budget, tracking, "-999.00", "monthly", TODAY + timedelta(days=5)
    )
    await create_scheduled_transaction(
        db_session,
        budget,
        checking,
        "-111.00",
        "monthly",
        TODAY + timedelta(days=3),
        is_deleted=True,
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=20)

    assert data["start_balance"] == Decimal("5000.00")
    _assert_bands_collapsed(data["points"])
    for p in data["points"]:
        assert p["p50"] == p["deterministic"] == Decimal("5000.00")
    assert data["events"] == []


async def test_a_closed_account_keeps_its_balance_but_generates_no_flows(db_session):
    """Closed accounts split by design: the residual BALANCE is still the
    budget's cash — `sum_on_budget_balance` includes closed accounts because
    closing moves no money, and the projection quoting a different cash figure
    than Ready to Assign is two answers to one question. But a closed account
    generates no FUTURE flows: its history is not sampled and its schedules
    fire nowhere. (Before the balance moved to `sum_on_budget_balance`, the
    projection silently dropped closed balances too.)"""
    budget, checking = await _budget_with_checking(db_session)
    closed = await create_account(db_session, budget, "Old Checking")
    await create_transaction(db_session, budget, closed, "777.00", TODAY - timedelta(days=200))
    # Inside the 180-day history window — would un-collapse the bands.
    await create_transaction(db_session, budget, closed, "-33.00", TODAY - timedelta(days=15))
    await create_scheduled_transaction(
        db_session, budget, closed, "-88.00", "monthly", TODAY + timedelta(days=4)
    )
    closed.is_closed = True
    await db_session.flush()

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=20)

    assert data["start_balance"] == Decimal("5744.00")  # 5000 + 777 − 33
    _assert_bands_collapsed(data["points"])
    for p in data["points"]:
        assert p["p50"] == p["deterministic"] == Decimal("5744.00")
    assert data["events"] == []


async def test_subscription_charges_project_monthly_from_last_charge(db_session):
    """The tag is read from the CATEGORY, and the charges are grouped by payee
    within it — the same question the Subscriptions report asks.

    This test used to tag a PAYEE, which is the only reason the projection
    looked alive: migration b8e5d1c73a49 deleted every payee-subscription row
    and made the routes refuse new ones, so in a real budget this had been
    projecting nothing since 2026-09-06. The test reached past the guard the
    product enforces, and so kept dead code green.
    """
    budget, checking = await _budget_with_checking(db_session)
    streaming = await _subscription_category(db_session, budget, "Streaming")
    netflix = await create_payee(db_session, budget, "Northstar Stream")

    # Billed mid-month: the last charge is the most recent billing day before
    # today, the one before it a calendar month earlier. Never today itself,
    # so the first projected charge is a move on the path, not its start.
    last_charge = TODAY.replace(day=14 if TODAY.day == 15 else 15)
    if last_charge >= TODAY:
        last_charge = add_months(last_charge, -1)
    for charged in (add_months(last_charge, -1), last_charge):
        await create_transaction(
            db_session, budget, checking, "-15.99", charged, payee=netflix, category=streaming
        )
    # A pending auth must shift neither the typical amount nor the cadence
    await create_transaction(
        db_session,
        budget,
        checking,
        "-99.00",
        TODAY - timedelta(days=10),
        payee=netflix,
        category=streaming,
        cleared="pending",
    )

    # "Monthly" means a CALENDAR month from the last charge, keeping the
    # subscription on its billing day. This used to step a flat 30 days, which
    # walks a monthly bill backwards through the calendar and fits thirteen
    # charges into a year. Derived rather than hardcoded, because the answer
    # depends on the month the test runs in.
    #
    # Two charges, not one. A single calendar month is 30 days long a third of
    # the time, and on those days a 30-day step gave the same date; no two
    # consecutive months are both 30 days, so the second charge always tells
    # the two apart. The guard below fails the test if that ever stops holding.
    charges = [add_months(last_charge, 1), add_months(last_charge, 2)]
    assert charges != [last_charge + timedelta(days=30), last_charge + timedelta(days=60)]
    horizon = (charges[-1] - TODAY).days

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=horizon)

    # The path carries both charges; the event list stops at 30 days out.
    assert _charged_dates(data["points"]) == charges
    assert [(e["date"], e["amount"], e["source"]) for e in data["events"]] == [
        (charge, Decimal("-15.99"), "subscription")
        for charge in charges
        if charge <= TODAY + timedelta(days=30)
    ]
    start = data["start_balance"]
    assert start == Decimal("4968.02")  # 5000 - two posted charges
    assert data["points"][horizon]["deterministic"] == start - Decimal("31.98")


async def test_scheduled_end_date_and_event_cap_respected(db_session):
    budget, checking = await _budget_with_checking(db_session)
    await create_scheduled_transaction(
        db_session,
        budget,
        checking,
        "-5.00",
        "weekly",
        TODAY + timedelta(days=2),
        end_date=TODAY + timedelta(days=9),
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)
    assert [e["date"] for e in data["events"]] == [
        TODAY + timedelta(days=2),
        TODAY + timedelta(days=9),
    ]

    # A daily schedule floods the 30-day event window; the list caps at 20
    budget2, checking2 = await _budget_with_checking(db_session)
    await create_scheduled_transaction(db_session, budget2, checking2, "-1.00", "daily", TODAY)
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


async def test_cards_contribute_neither_balance_nor_history_nor_schedules(db_session):
    """A card is on-budget, so the old inline balance sum included it and
    "Current Balance" read cash minus card debt — a figure with no name. The
    projection is CASH (`sum_on_budget_balance`): the card's balance, its
    ledger history, and any schedule pointed at it all stay out. Card spending
    reaches the projection only through the cash the payment moves."""
    budget, checking = await _budget_with_checking(db_session)
    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    # One purchase in the balance window only, one inside the 180-day history
    # window: the first used to lower start_balance, the second used to feed
    # the sampled flows and un-collapse the bands.
    await create_transaction(db_session, budget, card, "-1200.00", TODAY - timedelta(days=200))
    await create_transaction(db_session, budget, card, "-60.00", TODAY - timedelta(days=10))
    await create_scheduled_transaction(
        db_session, budget, card, "-45.00", "monthly", TODAY + timedelta(days=5)
    )

    result = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)

    assert result["start_balance"] == Decimal("5000.00")
    assert result["events"] == []
    _assert_bands_collapsed(result["points"])
    assert result["points"][-1]["deterministic"] == Decimal("5000.00")


async def test_a_twice_monthly_schedule_projects_every_occurrence(db_session):
    """The projection had its own copy of the recurrence stepping, and that
    copy had no `twice_monthly` branch: it returned None, the expansion loop
    read None as "schedule finished", and a twice-monthly schedule contributed
    exactly ONE occurrence to a 90-day projection.

    This is not a hypothetical shape. The sample budget gives its demo
    household a twice-monthly salary (`sample_budget/data.py`), so the demo
    projection was short most of its income while projecting every monthly
    bill in full — and `goes_negative_date` was computed off that.
    """
    budget, checking = await _budget_with_checking(db_session)
    payee = await create_payee(db_session, budget, "Northwind Payserv")
    # Paid on the 1st and the 15th from the 1st of next month, with the
    # horizon measured from that first payday. Measured from today, 90 days
    # held five paydays on most days and four on the 1st, so this test failed
    # about sixteen days a year.
    first = add_months(TODAY.replace(day=1), 1)
    horizon = (first - TODAY).days + 70
    await create_scheduled_transaction(
        db_session,
        budget,
        checking,
        "1900.00",
        "twice_monthly",
        first,
        payee=payee,
        start_date=first,
        second_day_of_month=15,
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=horizon)
    _assert_bands_collapsed(data["points"])

    # Seventy days from a 1st reach the 1st two months on (59–62 days) but not
    # the 15th after it (73–76). Listed by hand: walking `next_occurrence` to
    # build the expectation would test the stepping against itself.
    second, third = add_months(first, 1), add_months(first, 2)
    paydays = [first, first.replace(day=15), second, second.replace(day=15), third]
    assert _charged_dates(data["points"]) == paydays
    start = data["start_balance"]
    assert data["points"][horizon]["deterministic"] == start + Decimal("1900.00") * 5


async def test_a_month_end_schedule_keeps_its_day(db_session):
    """The old monthly branch stepped from the CLAMPED date, so a schedule
    dated the 31st read 28 Feb and then stayed on the 28th forever.
    `domain.schedule.next_occurrence` re-anchors to `start_date.day`.

    The charge dates are read back off the deterministic path and compared with
    a hand-written list. Walking the domain function to build the expectation
    would make this a tautology — the stepping is the thing under test.
    """
    budget, checking = await _budget_with_checking(db_session)
    payee = await create_payee(db_session, budget, "Harborstone Mortgage")
    year = TODAY.year + 1
    start = date(year, 1, 31)
    horizon = (date(year, 4, 5) - TODAY).days
    await create_scheduled_transaction(
        db_session,
        budget,
        checking,
        "-100.00",
        "monthly",
        start,
        payee=payee,
        start_date=start,
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=horizon)

    # February has no 31st, so that one occurrence clamps; March must return to
    # the 31st. The old code answered 28 Feb, then 28 Mar.
    assert _charged_dates(data["points"]) == [
        date(year, 1, 31),
        month_end(date(year, 2, 1)),
        date(year, 3, 31),
    ]


async def test_an_overdue_occurrence_lands_on_the_projected_path(db_session):
    """An occurrence already due but not yet entered used to appear in the
    events list under its own past date while never reaching the path — the
    path starts at today, so `det_by_date` held it under a date nobody visits.
    The user was shown a bill that no projected balance accounted for.
    """
    budget, checking = await _budget_with_checking(db_session)
    payee = await create_payee(db_session, budget, "Harborstone Insurance")
    await create_scheduled_transaction(
        db_session,
        budget,
        checking,
        "-250.00",
        "yearly",
        TODAY - timedelta(days=3),
        payee=payee,
        start_date=TODAY - timedelta(days=3),
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)
    start = data["start_balance"]

    # Booked on today, so the events list and the path agree.
    assert [e["date"] for e in data["events"]] == [TODAY]
    assert data["points"][0]["deterministic"] == start - Decimal("250.00")
    assert data["points"][30]["deterministic"] == start - Decimal("250.00")


async def test_a_long_cancelled_subscription_is_not_projected_forever(db_session):
    """The subscription query had no recency bound, so a payee last charged
    years ago still had a `max(date)`, and the walk stepped from that charge up
    to today and then booked every future cycle. A subscription that has missed
    two cycles is treated as cancelled.
    """
    budget, checking = await _budget_with_checking(db_session)
    streaming = await _subscription_category(db_session, budget, "Streaming")
    gone = await create_payee(db_session, budget, "Cascade Point Gym")

    # Two charges a month apart, both well outside two cycles of today.
    for days in (400, 370):
        await create_transaction(
            db_session,
            budget,
            checking,
            "-42.00",
            TODAY - timedelta(days=days),
            payee=gone,
            category=streaming,
        )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=90)
    assert [e for e in data["events"] if e["source"] == "subscription"] == []
    assert data["points"][90]["deterministic"] == data["start_balance"]


async def test_a_subscription_with_a_schedule_is_charged_once(db_session):
    """Both deterministic arms projected the same payee: the schedule arm from
    the schedule, the subscription arm from the payee's own charge history. A
    subscription the user had also entered as a scheduled transaction was
    therefore charged to the projection twice.
    """
    budget, checking = await _budget_with_checking(db_session)
    streaming = await _subscription_category(db_session, budget, "Streaming")
    payee = await create_payee(db_session, budget, "Northstar Stream")

    for days in (55, 25):
        await create_transaction(
            db_session,
            budget,
            checking,
            "-20.00",
            TODAY - timedelta(days=days),
            payee=payee,
            category=streaming,
        )
    await create_scheduled_transaction(
        db_session,
        budget,
        checking,
        "-20.00",
        "monthly",
        TODAY + timedelta(days=6),
        payee=payee,
        start_date=TODAY + timedelta(days=6),
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)

    sources = [e["source"] for e in data["events"]]
    assert sources == ["scheduled"], f"the subscription arm booked it too: {sources}"
    start = data["start_balance"]
    # One charge in the window, not two.
    assert data["points"][30]["deterministic"] == start - Decimal("20.00")


async def test_a_scheduled_bill_is_not_also_sampled_from_history(db_session):
    """The two layers have to partition the register. The sampled history had
    no exclusion for the rows the deterministic layer re-applies, so every
    scheduled bill landed in a simulated path twice — once sampled out of its
    own history, once added from `det_by_date` — biasing p50 and
    `goes_negative_date` by the whole recurring load.

    Here the ONLY history is the bill itself, so before the fix the sampled
    flow was a non-zero constant and the bands could not collapse onto the
    deterministic path. After it, the residual history is empty and they do.
    """
    budget, checking = await _budget_with_checking(db_session)
    payee = await create_payee(db_session, budget, "Harborstone Rent")

    # Six monthly rent charges inside the 180-day history window.
    for months_back in range(1, 7):
        await create_transaction(
            db_session,
            budget,
            checking,
            "-1800.00",
            add_months(TODAY, -months_back),
            payee=payee,
        )
    await create_scheduled_transaction(
        db_session,
        budget,
        checking,
        "-1800.00",
        "monthly",
        add_months(TODAY, 1),
        payee=payee,
        start_date=add_months(TODAY, 1),
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=60)

    # No residual variation left, so every band sits on the deterministic path.
    _assert_bands_collapsed(data["points"])
    for p in data["points"]:
        assert p["p50"] == p["deterministic"]


async def test_rows_with_no_payee_stay_in_the_sampled_history(db_session):
    """The exclusion was `payee_id NOT IN (every scheduled payee)`, and SQL's
    NOT IN is unknown for a NULL payee — so the moment one schedule carried a
    payee, every payee-less row left the history. That is every split line
    typed in the UI: the legs carry categories, the parent carries the payee.

    Uniform history of -10 a day, half of it split legs and half plain rows
    with no payee, beside an unrelated $1 schedule with a payee. Before, the
    sampled flow was 0 and "goes negative in 10 days" read as never.
    """
    budget, checking = await _budget_with_checking(db_session, opening="310.00")
    market = await create_payee(db_session, budget, "Harborstone Market")
    gym = await create_payee(db_session, budget, "Cascade Point Gym")
    for days_back in range(1, 22):
        day = TODAY - timedelta(days=days_back)
        if days_back % 2:
            await create_transaction(db_session, budget, checking, "-10.00", day)
            continue
        parent = await create_transaction(
            db_session, budget, checking, "-10.00", day, payee=market, is_split=True
        )
        for leg in ("-6.00", "-4.00"):
            await create_transaction(
                db_session, budget, checking, leg, day, parent_transaction_id=parent.id
            )
    await create_scheduled_transaction(
        db_session, budget, checking, "-1.00", "monthly", TODAY + timedelta(days=5), payee=gym
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)
    _assert_sampled_flow_per_day(data["points"], Decimal("-10"))


async def test_a_split_bill_leaves_the_history_with_its_schedule(db_session):
    """The other half of the payee rule: a split's legs carry no payee of their
    own, so matching a schedule to its bill has to read the parent's. Keyed on
    the leg's own payee column, a rent payment split into rent and a fee would
    stay in the history beside the schedule that projects it."""
    budget, checking = await _budget_with_checking(db_session)
    landlord = await create_payee(db_session, budget, "Harborstone Rent")
    for months_back in range(1, 6):
        day = add_months(TODAY, -months_back)
        parent = await create_transaction(
            db_session, budget, checking, "-1800.00", day, payee=landlord, is_split=True
        )
        for leg in ("-1750.00", "-50.00"):
            await create_transaction(
                db_session, budget, checking, leg, day, parent_transaction_id=parent.id
            )
    await create_scheduled_transaction(
        db_session, budget, checking, "-1800.00", "monthly", add_months(TODAY, 1), payee=landlord
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=60)
    _assert_sampled_flow_per_day(data["points"], Decimal("0"))


async def test_a_subscription_payees_other_spending_stays_sampled(db_session):
    """The subscription arm projects a payee's Subscription-tagged charges, and
    the exclusion took every row of that payee in every category. A warehouse
    with a $15 membership and $10 a day of household shopping lost the
    shopping from both layers: the fixed layer never had it, and the sampled
    one threw it away.
    """
    budget, checking = await _budget_with_checking(db_session)
    membership = await _subscription_category(db_session, budget, "Warehouse Membership")
    group = await create_category_group(db_session, budget, "Home")
    household = await create_category(db_session, budget, group, "Household")
    megastore = await create_payee(db_session, budget, "Megastore")
    for days_back in (45, 15):
        await create_transaction(
            db_session,
            budget,
            checking,
            "-15.00",
            TODAY - timedelta(days=days_back),
            payee=megastore,
            category=membership,
        )
    for days_back in range(1, 22):
        await create_transaction(
            db_session,
            budget,
            checking,
            "-10.00",
            TODAY - timedelta(days=days_back),
            payee=megastore,
            category=household,
        )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)

    assert [e["source"] for e in data["events"]] == ["subscription"]
    # The membership charges are the fixed layer's; the shopping is all that
    # is left to sample, at exactly -10 a day.
    _assert_sampled_flow_per_day(data["points"], Decimal("-10"))


async def test_a_schedule_made_in_the_editor_is_charged_once(db_session):
    """IGAB's schedule editor has no payee field, and "Make repeating" carries
    the category and account but not the payee. The dedup keyed on the
    schedule's payee, so a subscription turned into a schedule in the app was
    charged by both arms: -$40 a cycle for a $20 service.
    """
    budget, checking = await _budget_with_checking(db_session)
    streaming = await _subscription_category(db_session, budget, "Streaming")
    payee = await create_payee(db_session, budget, "Northstar Stream")
    for days in (55, 25):
        await create_transaction(
            db_session,
            budget,
            checking,
            "-20.00",
            TODAY - timedelta(days=days),
            payee=payee,
            category=streaming,
        )
    # The editor's shape: category and account, no payee.
    await create_scheduled_transaction(
        db_session,
        budget,
        checking,
        "-20.00",
        "monthly",
        TODAY + timedelta(days=6),
        category=streaming,
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=30)

    assert [e["source"] for e in data["events"]] == ["scheduled"]
    assert data["points"][30]["deterministic"] == data["start_balance"] - Decimal("20.00")


async def test_an_editor_schedules_bill_leaves_the_history(db_session):
    """The same missing payee on the history side: a rent schedule made in the
    editor left the bank-synced rent rows in the sampled history, so the path
    paid rent twice. With no payee, the bill is its category on its account."""
    budget, checking = await _budget_with_checking(db_session)
    group = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, group, "Rent")
    landlord = await create_payee(db_session, budget, "Harborstone Rent")
    for months_back in range(1, 6):
        await create_transaction(
            db_session,
            budget,
            checking,
            "-1800.00",
            add_months(TODAY, -months_back),
            payee=landlord,
            category=rent,
        )
    await create_scheduled_transaction(
        db_session, budget, checking, "-1800.00", "monthly", add_months(TODAY, 1), category=rent
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=60)
    _assert_sampled_flow_per_day(data["points"], Decimal("0"))


async def test_a_refund_into_a_scheduled_bills_envelope_stays_sampled(db_session):
    """A schedule stands in for money moving its own way. A +50 refund filed
    to Rent is not rent, and the fixed layer never re-applies it."""
    budget, checking = await _budget_with_checking(db_session)
    group = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, group, "Rent")
    for months_back in range(1, 6):
        await create_transaction(
            db_session, budget, checking, "-1800.00", add_months(TODAY, -months_back), category=rent
        )
    await create_transaction(
        db_session, budget, checking, "50.00", TODAY - timedelta(days=3), category=rent
    )
    await create_scheduled_transaction(
        db_session, budget, checking, "-1800.00", "monthly", add_months(TODAY, 1), category=rent
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=60)
    # The refund is the only history left, so every weekday samples it.
    _assert_sampled_flow_per_day(data["points"], Decimal("50"))


async def test_a_stale_reminder_schedule_books_one_overdue_occurrence(db_session):
    """A manual schedule advances only when someone presses Enter or Skip. Kept
    as a reminder for a bill paid through bank sync, it piles up missed
    occurrences whose money has already left — and every one of them was
    booked on today, so a stale reminder alone could read "goes negative
    today". Everything due by today is one charge on the path: the one row
    the register shows.

    Weekly, first due 185 days ago: 27 occurrences before today, the next one
    four days out.
    """
    budget, checking = await _budget_with_checking(db_session)
    payee = await create_payee(db_session, budget, "Harborstone Rent")
    first_due = TODAY - timedelta(days=185)
    await create_scheduled_transaction(
        db_session, budget, checking, "-100.00", "weekly", first_due, payee=payee
    )

    data = await ReportService(db_session).cash_projection(budget.id, horizon_days=5)

    assert [e["date"] for e in data["events"]] == [TODAY, TODAY + timedelta(days=4)]
    start = data["start_balance"]
    assert data["points"][0]["deterministic"] == start - Decimal("100.00")
    assert data["points"][5]["deterministic"] == start - Decimal("200.00")
