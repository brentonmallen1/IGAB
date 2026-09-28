"""A plan-family figure opens the rows it totals.

Plan vs Spent, Volatility and Anomalies read the plan
ledger's spent — net of refunds, a Savings envelope's transfer out counted,
money moved into or out of an ordinary envelope not. Their drills asked for the
category's `direction=outflow` rows instead, so a month with a refund opened a
list totalling more than its figure, and a brokerage transfer out of an
untagged envelope was listed under a figure that never counted it. They ask
for `plan_spent` now (`repositories/plan_rows.py`), which is `plan_effect`'s
own verdict as a WHERE clause.

Each test holds a figure to the listing its drill opens. Amounts are invented
and round.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from igab.domain.dates import add_months, month_end
from igab.repositories.txn_query import TransactionFilters, build_where
from igab.services.report_service import ReportService
from tests.report_clock import report_today

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
    money,
    tag_with_system_tags,
)

D = Decimal
TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)
LAST_MONTH = add_months(THIS_MONTH, -1)


@pytest.fixture(autouse=True)
def _pinned_today():
    with report_today(TODAY):
        yield


def back(n: int) -> date:
    return add_months(THIS_MONTH, -n)


async def _world(db_session, user):
    """Groceries (untagged) with six ordinary months and one busy one: 700
    bought, 100 refunded, 250 sent to a brokerage, 40 moved in from savings.
    Vacation Savings (tagged) sends 300 on to the HYSA and spends 50."""
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    hysa = await create_account(
        db_session, budget, "Cascade Point HYSA", account_type="savings", on_budget=False
    )
    brokerage = await create_account(
        db_session, budget, "Cascade Brokerage", account_type="investment", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    vacation = await create_category(db_session, budget, group, "Vacation Savings")
    await tag_with_system_tags(db_session, vacation, "savings")

    for n, amount in zip(range(7, 1, -1), ("70", "130", "90", "110", "100", "100"), strict=True):
        await create_budget_assignment(db_session, budget, groceries, back(n), "100.00")
        await create_transaction(
            db_session, budget, checking, f"-{amount}.00", back(n), category=groceries
        )

    await create_budget_assignment(db_session, budget, groceries, LAST_MONTH, "600.00")
    await create_transaction(
        db_session, budget, checking, "-700.00", LAST_MONTH, category=groceries
    )
    await create_transaction(db_session, budget, checking, "100.00", LAST_MONTH, category=groceries)
    await create_transfer(
        db_session, budget, checking, brokerage, "250.00", LAST_MONTH, category=groceries
    )
    _, into = await create_transfer(db_session, budget, hysa, checking, "40.00", LAST_MONTH)
    into.category_id = groceries.id

    await create_budget_assignment(db_session, budget, vacation, LAST_MONTH, "400.00")
    await create_transfer(
        db_session, budget, checking, hysa, "300.00", LAST_MONTH, category=vacation
    )
    await create_transaction(db_session, budget, checking, "-50.00", LAST_MONTH, category=vacation)
    await db_session.commit()
    return budget, groceries, vacation


async def _drilled(api_client, budget, category_id, start: date, end: date, **extra) -> Decimal:
    """What the drill panel totals: the listing the plan-family drills open.
    `category_id` None is a drill over every category — a month total's."""
    params = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "scope": "leaf",
        "posted_only": "true",
        "cash_flow_only": "true",
        "plan_spent": "true",
        "limit": 500,
        **({"category_ids": str(category_id)} if category_id else {}),
        **extra,
    }
    r = await api_client.get(f"/api/v1/{budget.id}/transactions", params=params)
    assert r.status_code == 200, r.text
    return money(r.json()["total_amount"])


class TestTheDrillTotalsTheFigure:
    async def test_budget_vs_actual(self, db_session, api_client):
        budget, groceries, vacation = await _world(db_session, api_client.test_user)
        end = month_end(LAST_MONTH)
        bva = await ReportService(db_session).budget_vs_actual(budget.id, LAST_MONTH, end)

        spent = {c["category_id"]: c["spent"] for c in bva["categories"]}
        # 700 - 100 refunded; the brokerage transfer and the 40 moved in are not spent.
        assert spent[str(groceries.id)] == D("600")
        # The HYSA transfer out of a Savings envelope is.
        assert spent[str(vacation.id)] == D("350")
        for cat in (groceries, vacation):
            drilled = await _drilled(api_client, budget, cat.id, LAST_MONTH, end)
            assert -drilled == spent[str(cat.id)], cat.name

    async def test_the_outflow_list_it_used_to_open_did_not(self, db_session, api_client):
        """The old drill: the category's outflows. 950 under a 600 figure —
        the refund dropped, the brokerage transfer listed."""
        budget, groceries, _ = await _world(db_session, api_client.test_user)
        end = month_end(LAST_MONTH)
        old = await _drilled(
            api_client,
            budget,
            groceries.id,
            LAST_MONTH,
            end,
            plan_spent="false",
            direction="outflow",
        )
        assert old == D("-950")

    async def test_plan_vs_spent_every_cell(self, db_session, api_client):
        budget, *_ = await _world(db_session, api_client.test_user)
        pvr = await ReportService(db_session).plan_vs_spent(budget.id, months=12)

        checked = 0
        for cat in pvr["categories"]:
            for cell in cat["monthly"]:
                if not cell["active"]:
                    continue
                m = cell["month"]
                drilled = await _drilled(
                    api_client, budget, cat["category_id"], m, min(month_end(m), TODAY)
                )
                assert -drilled == cell["spent"], (cat["category_name"], m)
                checked += 1
        assert checked >= 8

    async def test_plan_vs_spent_every_total(self, db_session, api_client):
        """The Total column, the totals row and the window's Spent each open
        the rows they count: a category over the complete months, a month over
        every category, and the complete months over every category."""
        budget, groceries, vacation = await _world(db_session, api_client.test_user)
        report = await ReportService(db_session).plan_vs_spent(budget.id, months=12)
        start, end = report["totals_start"], report["totals_end"]

        for cat in report["categories"]:
            drilled = await _drilled(api_client, budget, cat["category_id"], start, end)
            assert -drilled == cat["total"]["spent"], cat["category_name"]
        assert _row(report, groceries)["total"]["spent"] == D("1200")
        assert _row(report, vacation)["total"]["spent"] == D("350")

        for point in report["month_totals"]:
            m = point["month"]
            drilled = await _drilled(api_client, budget, None, m, min(month_end(m), TODAY))
            assert -drilled == point["spent"], m

        assert -(await _drilled(api_client, budget, None, start, end)) == report["total_spent"]
        assert report["total_spent"] == D("1550")

    async def test_a_scoped_total_opens_the_scope(self, db_session, api_client):
        """Scoped to Groceries, the month total counts Groceries alone, and so
        does a drill carrying the same scope."""
        budget, groceries, _ = await _world(db_session, api_client.test_user)
        report = await ReportService(db_session).plan_vs_spent(
            budget.id, months=12, category_ids=[groceries.id]
        )
        (last,) = [p for p in report["month_totals"] if p["month"] == LAST_MONTH]
        drilled = await _drilled(
            api_client, budget, groceries.id, LAST_MONTH, month_end(LAST_MONTH)
        )
        assert last["spent"] == -drilled == D("600")

    async def test_volatility(self, db_session, api_client):
        budget, groceries, _ = await _world(db_session, api_client.test_user)
        vol = await ReportService(db_session).category_volatility(budget.id, months=12)
        (row,) = [c for c in vol["categories"] if c["category_id"] == str(groceries.id)]

        drilled = await _drilled(
            api_client, budget, groceries.id, vol["window_start"], vol["window_end"]
        )
        # The figure is a mean over the window's months; the list is its total.
        assert abs(row["mean"] * row["months_included"] + drilled) < D("0.01")
        assert -drilled == D("1200")

    async def test_anomalies(self, db_session, api_client):
        budget, groceries, _ = await _world(db_session, api_client.test_user)
        report = await ReportService(db_session).anomalies_report(budget.id, months=12)
        (spike,) = [
            a
            for a in report["anomalies"]
            if a["category_id"] == str(groceries.id) and a["month"] == LAST_MONTH
        ]

        drilled = await _drilled(
            api_client, budget, groceries.id, LAST_MONTH, month_end(LAST_MONTH)
        )
        assert spike["actual"] == D("600")
        assert -drilled == spike["actual"]


def _row(report: dict, category) -> dict:
    return next(c for c in report["categories"] if c["category_id"] == str(category.id))


def test_the_filter_asks_for_the_class_joins():
    """It reads `ACTIVITY_CLASS`; without the joins the listing is a
    cartesian product (a test failure, by `pyproject.toml`)."""
    budget_id = uuid.uuid4()
    assert build_where(budget_id, TransactionFilters(plan_spent=True)).class_joins is True
    assert build_where(budget_id, TransactionFilters()).class_joins is False
