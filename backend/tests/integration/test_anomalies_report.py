"""Anomaly detection: leave-one-out z-scores over category-month spending.

Pins the detection contract:
- z = (actual − mean(others)) / std(others), others = all other months for
  that category (population std). Needs ≥ 6 category-months of history.
- Guard rails pin intentional silences: std < 5 (flat baselines never flag,
  even for huge spikes) and |actual − mean| < 25 (small-dollar wobble).
- System category groups are invisible to the detector.
- Known limitation, documented: months with zero spending produce no row,
  so they are absent from the baseline rather than counted as 0.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
)

TODAY = date.today()


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


async def _spend_series(db_session, budget, account, category, series: dict[int, str]):
    """Create one posted outflow per {months_ago: amount} entry."""
    for k, amount in series.items():
        await create_transaction(
            db_session, budget, account, f"-{amount}", months_ago(k), category=category
        )


async def test_spike_flags_with_exact_leave_one_out_zscore(db_session):
    budget, checking, group = await _setup(db_session)
    groceries = await create_category(db_session, budget, group, "Groceries")

    # Baseline alternates 80/120 (mean 100, population std 20)
    await _spend_series(
        db_session,
        budget,
        checking,
        groceries,
        {6: "80.00", 5: "120.00", 4: "80.00", 3: "120.00", 2: "80.00", 1: "120.00"},
    )
    # Spike month is built from split children + noise that must not count
    parent = await create_transaction(
        db_session, budget, checking, "-300.00", months_ago(0), is_split=True
    )
    for child_amount in ("-150.00", "-150.00"):
        await create_transaction(
            db_session,
            budget,
            checking,
            child_amount,
            months_ago(0),
            category=groceries,
            parent_transaction_id=parent.id,
        )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-100.00",
        months_ago(0),
        category=groceries,
        cleared="pending",
    )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-50.00",
        months_ago(0),
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
        {6: "80.00", 5: "120.00", 4: "80.00", 3: "120.00", 2: "80.00", 1: "120.00", 0: "300.00"},
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)

    assert len(data["anomalies"]) == 1
    a = data["anomalies"][0]
    assert a["category_name"] == "Groceries"
    assert a["month"] == months_ago(0)
    assert a["actual"] == Decimal("300.00")
    assert a["baseline_mean"] == Decimal("100.00")
    assert a["z_score"] == pytest.approx(10.0)  # (300 - 100) / 20
    assert a["direction"] == "high"
    expected_history = [Decimal("0.00")] * 5 + [
        Decimal("80.00"),
        Decimal("120.00"),
        Decimal("80.00"),
        Decimal("120.00"),
        Decimal("80.00"),
        Decimal("120.00"),
        Decimal("300.00"),
    ]
    assert a["history"] == expected_history


async def test_threshold_parameter_bounds_detection(db_session):
    budget, checking, group = await _setup(db_session)
    dining = await create_category(db_session, budget, group, "Dining")

    # Baseline mean 120, std 20; 170 gives z = 2.5
    await _spend_series(
        db_session,
        budget,
        checking,
        dining,
        {6: "100.00", 5: "140.00", 4: "100.00", 3: "140.00", 2: "100.00", 1: "140.00", 0: "170.00"},
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
    # Small wobble: z = 2.0 but |actual - mean| = 20 < 25 stays silent
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
        {6: "180.00", 5: "220.00", 4: "180.00", 3: "220.00", 2: "180.00", 1: "220.00", 0: "40.00"},
    )

    data = await ReportService(db_session).anomalies_report(budget.id, months=12)

    assert len(data["anomalies"]) == 1
    a = data["anomalies"][0]
    assert a["direction"] == "low"
    assert a["z_score"] == pytest.approx(-8.0)  # (40 - 200) / 20


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
