"""Anomaly detection: z-scores over category-month spending.

Pins the detection contract (`report_stats.anomaly_scan`):
- z = (actual − mean(earlier)) / σ(earlier), where earlier is the category's
  complete months BEFORE the one scored and σ the sample deviation (n − 1),
  the σ Volatility reports. A month needs 6 earlier months behind it.
- A quiet month is a zero, from the category's first spending in the window.
  (Months without rows used to be absent from the baseline instead.)
- Guard rails pin intentional silences: σ < 5 (flat baselines never flag,
  even for huge spikes) and |actual − mean| < 25 (small-dollar wobble).
- Spent is the plan ledger's: net of refunds, system groups invisible.
- Sinking funds are not tested, and the response says how many categories
  were.
- The month in progress is scored but flags only HIGH.

Every baseline below has mean and sample σ round enough to check on paper:
deviations of ±30, ±10, 0, 0 around the mean square-sum to 2,000, which over
five is a σ of exactly 20.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.services.report_service import ReportService
from tests.report_clock import report_today

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
)

TODAY = date.today()


@pytest.fixture(autouse=True)
def _the_service_reads_this_modules_today():
    """Rows are dated from TODAY, read once at import; the report reads the
    clock when called. A run that crossed midnight on a month's last day asked
    a service that already called the seeded "current month" complete, so the
    partial-month test scored its 12.00 against a 400 baseline and flagged it.
    Pinned, every test asks the day its rows were seeded for."""
    with report_today(TODAY):
        yield


def months_ago(n: int) -> date:
    year, month = TODAY.year, TODAY.month - n
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


async def _setup(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    return budget, checking, group


def newest_scorable() -> date:
    """The newest COMPLETE month: the last one scored in either direction.

    The month in progress is scored too, but only a HIGH verdict on it
    survives — `report_stats.anomaly_scan` says why. A test that wants a LOW
    flag, or a baseline month, puts it here.
    """
    return months_ago(1)


async def _spend_series(db_session, budget, account, category, series: dict[int, str]):
    """Create one posted outflow per {months back from `newest_scorable`: amount}.

    Offsets are relative to the newest SCORABLE month rather than to today, so
    `0` means "the most recent month this report looks at" in every series.
    """
    for k, amount in series.items():
        await create_transaction(
            db_session, budget, account, f"-{amount}", months_ago(k + 1), category=category
        )


async def test_spike_flags_with_exact_leave_one_out_zscore(db_session):
    budget, checking, group = await _setup(db_session)
    groceries = await create_category(db_session, budget, group, "Groceries")

    # Baseline 70/130/90/110/100/100: mean 100, sample σ 20
    await _spend_series(
        db_session,
        budget,
        checking,
        groceries,
        {6: "70.00", 5: "130.00", 4: "90.00", 3: "110.00", 2: "100.00", 1: "100.00"},
    )
    # Spike month is built from split children + noise that must not count
    parent = await create_transaction(
        db_session, budget, checking, "-300.00", newest_scorable(), is_split=True
    )
    for child_amount in ("-150.00", "-150.00"):
        await create_transaction(
            db_session,
            budget,
            checking,
            child_amount,
            newest_scorable(),
            category=groceries,
            parent_transaction_id=parent.id,
        )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-100.00",
        newest_scorable(),
        category=groceries,
        cleared="pending",
    )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-50.00",
        newest_scorable(),
        category=groceries,
        is_deleted=True,
    )
    # Identical spike in a system group: must stay invisible
    sys_group = await create_category_group(db_session, budget, "System", is_system=True)
    sys_cat = await create_category(db_session, budget, sys_group, "Hidden")
    await _spend_series(
        db_session,
        budget,
        checking,
        sys_cat,
        {6: "70.00", 5: "130.00", 4: "90.00", 3: "110.00", 2: "100.00", 1: "100.00", 0: "300.00"},
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)

    assert len(data["anomalies"]) == 1
    a = data["anomalies"][0]
    assert a["category_name"] == "Groceries"
    assert a["month"] == newest_scorable()
    assert a["actual"] == Decimal("300.00")
    assert a["baseline_mean"] == Decimal("100.00")
    assert a["z_score"] == pytest.approx(10.0)  # (300 - 100) / 20
    assert a["direction"] == "high"
    assert a["partial_month"] is False
    assert (a["usual_low"], a["usual_high"]) == (Decimal("80.00"), Decimal("120.00"))
    # Twelve calendar months ending with the spike; the five before the
    # category's first spending are absent, not zero.
    expected_history = [None] * 5 + [
        Decimal("70.00"),
        Decimal("130.00"),
        Decimal("90.00"),
        Decimal("110.00"),
        Decimal("100.00"),
        Decimal("100.00"),
        Decimal("300.00"),
    ]
    assert a["history"] == expected_history
    assert (data["categories_seen"], data["categories_tested"]) == (1, 1)


async def test_threshold_parameter_bounds_detection(db_session):
    budget, checking, group = await _setup(db_session)
    dining = await create_category(db_session, budget, group, "Dining")

    # Baseline mean 120, sample σ 20; 170 gives z = 2.5
    await _spend_series(
        db_session,
        budget,
        checking,
        dining,
        {6: "90.00", 5: "150.00", 4: "110.00", 3: "130.00", 2: "120.00", 1: "120.00", 0: "170.00"},
    )

    reports = ReportService(db_session)
    at_default = await reports.anomalies_report(budget.id, months=12, threshold=2.0)
    assert len(at_default["anomalies"]) == 1
    assert at_default["anomalies"][0]["z_score"] == pytest.approx(2.5)

    at_three = await reports.anomalies_report(budget.id, months=12, threshold=3.0)
    assert at_three["anomalies"] == []


async def test_guard_rails_silence_flat_and_small_dollar_baselines(db_session):
    budget, checking, group = await _setup(db_session)

    # Flat baseline: std = 0 < 5, so even a 3x spike stays silent
    flat = await create_category(db_session, budget, group, "Flat")
    await _spend_series(
        db_session,
        budget,
        checking,
        flat,
        {6: "100.00", 5: "100.00", 4: "100.00", 3: "100.00", 2: "100.00", 1: "100.00", 0: "300.00"},
    )
    # Small wobble: |actual - mean| = 20 < 25 stays silent
    wobble = await create_category(db_session, budget, group, "Wobble")
    await _spend_series(
        db_session,
        budget,
        checking,
        wobble,
        {6: "100.00", 5: "120.00", 4: "100.00", 3: "120.00", 2: "100.00", 1: "120.00", 0: "130.00"},
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)
    assert data["anomalies"] == []


async def test_low_side_anomaly_flags_with_direction_low(db_session):
    budget, checking, group = await _setup(db_session)
    fuel = await create_category(db_session, budget, group, "Fuel")

    await _spend_series(
        db_session,
        budget,
        checking,
        fuel,
        {6: "170.00", 5: "230.00", 4: "190.00", 3: "210.00", 2: "200.00", 1: "200.00", 0: "40.00"},
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)

    assert len(data["anomalies"]) == 1
    a = data["anomalies"][0]
    assert a["direction"] == "low"
    assert a["z_score"] == pytest.approx(-8.0)  # (40 - 200) / 20
    assert (a["usual_low"], a["usual_high"]) == (Decimal("180.00"), Decimal("220.00"))


async def test_fewer_than_six_category_months_never_flags(db_session):
    budget, checking, group = await _setup(db_session)
    sparse = await create_category(db_session, budget, group, "Sparse")

    await _spend_series(
        db_session,
        budget,
        checking,
        sparse,
        {4: "100.00", 3: "100.00", 2: "100.00", 1: "100.00", 0: "900.00"},
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)
    assert data["anomalies"] == []


async def _baseline_around_400(db_session, budget, checking, groceries):
    """Six complete months averaging 400. Varied on purpose: a perfectly flat
    history falls under the std < 5 guard and would pass whatever the window
    did, while the spread is small enough that no complete month clears the
    25.00 deviation guard — so the month in progress is the only candidate."""
    await _spend_series(
        db_session,
        budget,
        checking,
        groceries,
        {5: "380.00", 4: "420.00", 3: "390.00", 2: "410.00", 1: "400.00", 0: "400.00"},
    )


async def test_the_month_in_progress_is_never_flagged_low(db_session):
    """A partial month is not a small month.

    The month in progress used to be scored as a full observation against a
    baseline of complete ones, so on the 2nd of every month every established
    category read anomalously LOW — a household spending 400 on groceries was
    told its grocery spending had collapsed, every month, for most of the
    month. It is still scored, but only a HIGH verdict on it survives.
    """
    budget, checking, group = await _setup(db_session)
    groceries = await create_category(db_session, budget, group, "Groceries")
    await _baseline_around_400(db_session, budget, checking, groceries)
    await create_transaction(
        db_session, budget, checking, "-12.00", months_ago(0), category=groceries
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)

    assert data["anomalies"] == []


async def test_a_spike_in_the_month_in_progress_flags_and_says_it_is_partial(db_session):
    """Waiting for the month to close hid a 3x grocery month for up to 31 days.

    Spending only accumulates, so a partial month cannot fake a HIGH: the
    spike is real the day it happens, and the row says the month is not over.
    """
    budget, checking, group = await _setup(db_session)
    groceries = await create_category(db_session, budget, group, "Groceries")
    await _baseline_around_400(db_session, budget, checking, groceries)
    await create_transaction(
        db_session, budget, checking, "-1200.00", months_ago(0), category=groceries
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)

    assert len(data["anomalies"]) == 1
    a = data["anomalies"][0]
    assert a["month"] == months_ago(0)
    assert a["actual"] == Decimal("1200.00")
    assert a["baseline_mean"] == Decimal("400.00")
    assert a["direction"] == "high"
    assert a["partial_month"] is True


async def test_a_quiet_month_is_a_zero(db_session):
    """300, nothing, 200, 100, 150, 150 and then 750. The quiet month has no
    row; counted as a zero the baseline is mean 150, σ 100, and the spike is
    6 σ. Skipped, the baseline was five busy months at a mean of 180."""
    budget, checking, group = await _setup(db_session)
    gifts = await create_category(db_session, budget, group, "Gifts")
    await _spend_series(
        db_session,
        budget,
        checking,
        gifts,
        {6: "300.00", 4: "200.00", 3: "100.00", 2: "150.00", 1: "150.00", 0: "750.00"},
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)

    (a,) = data["anomalies"]
    assert a["baseline_mean"] == Decimal("150.00")
    assert a["z_score"] == pytest.approx(6.0)
    assert a["history"][-7:] == [
        Decimal("300.00"),
        Decimal("0.00"),
        Decimal("200.00"),
        Decimal("100.00"),
        Decimal("150.00"),
        Decimal("150.00"),
        Decimal("750.00"),
    ]


async def test_a_refund_nets_the_month(db_session):
    """Spent is net, as every plan report counts it. A 700 purchase returned
    for 490 the same month is 210 of spending — inside the baseline's range,
    not the 3.5x spike the gross outflow read as."""
    budget, checking, group = await _setup(db_session)
    home = await create_category(db_session, budget, group, "Home")
    await _spend_series(
        db_session,
        budget,
        checking,
        home,
        {6: "170.00", 5: "230.00", 4: "190.00", 3: "210.00", 2: "200.00", 1: "200.00", 0: "700.00"},
    )
    await create_transaction(
        db_session, budget, checking, "490.00", newest_scorable(), category=home
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)

    assert data["anomalies"] == []


async def test_a_sinking_fund_is_not_tested(db_session):
    """Months of nothing and then the premium it saved for is the plan
    working. Flagged, the most disciplined envelope read as the least."""
    from igab.repositories.tag_repo import TagRepository, seed_system_tags

    budget, checking, group = await _setup(db_session)
    premium = await create_category(db_session, budget, group, "Car Insurance")
    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    fund = await tags.get_system_tag(budget.id, "long_term_expense")
    await tags.set_category_tags(premium.id, [fund.id])
    await _spend_series(
        db_session,
        budget,
        checking,
        premium,
        {6: "70.00", 5: "130.00", 4: "90.00", 3: "110.00", 2: "100.00", 1: "100.00", 0: "900.00"},
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)

    assert data["anomalies"] == []
    assert data["sinking_funds_skipped"] == 1
    assert (data["categories_seen"], data["categories_tested"]) == (0, 0)


async def test_it_says_how_many_categories_it_could_test(db_session):
    """An empty report owes its reader "N of M categories tested": a young
    category with three months cannot be scored, which is not the same as
    being normal."""
    budget, checking, group = await _setup(db_session)
    steady = await create_category(db_session, budget, group, "Groceries")
    young = await create_category(db_session, budget, group, "Pet")
    await _spend_series(
        db_session,
        budget,
        checking,
        steady,
        {6: "400.00", 5: "400.00", 4: "400.00", 3: "400.00", 2: "400.00", 1: "400.00", 0: "400.00"},
    )
    await _spend_series(db_session, budget, checking, young, {2: "50.00", 1: "50.00", 0: "50.00"})

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)

    assert data["anomalies"] == []
    assert (data["categories_seen"], data["categories_tested"]) == (2, 1)
    assert data["sinking_funds_skipped"] == 0
