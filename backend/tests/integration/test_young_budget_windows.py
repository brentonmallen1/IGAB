"""A young budget's averages divide by the months it has, in every report.

"All time" counts the running month — `available_range` is every month the
history touches — while an averaging report reads COMPLETE months. So "All
time" on a budget three complete months old asked for four, and the window
reached one month before the first transaction. Volatility, seasonality and
anomalies clamped to the history (`ReportService._complete_window`); Income
by Source, Cost of Living, Discretionary, Subscriptions and the Essentials
table called the arithmetic without it, and divided three months of rent by
four: every figure a quarter low, on the setting that promises the most.

One rule now (`report_basics.history_window`). Each report below is named
by the test that pins it, on the default twelve months and on "All time".

The household: three complete months of a 3,000 paycheck, 1,200 rent
(Essential), 300 dining and a 15 streaming charge (Subscription), plus a
running month that no average reads. Every figure is written by hand.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.dates import add_months
from igab.services.essentials import essentials_summary
from igab.services.report_basics import (
    cost_of_living,
    discretionary,
    income_by_source,
    subscriptions_report,
)
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
    tag_with_system_tags,
)

D = Decimal
#: The reader's day, passed to every report: the fixture is built for it, so
#: a run that crosses midnight cannot move the window under the rows.
TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)
#: The three complete months the history holds, oldest first.
HISTORY = [add_months(THIS_MONTH, -n) for n in (3, 2, 1)]


async def _young_household(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    sysgroup = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, sysgroup, "Ready to Assign")
    bills = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, bills, "Rent")
    await tag_with_system_tags(db_session, rent, "essential")
    fun = await create_category_group(db_session, budget, "Fun")
    dining = await create_category(db_session, budget, fun, "Dining")
    streaming = await create_category(db_session, budget, fun, "Streaming")
    await tag_with_system_tags(db_session, streaming, "subscription")
    payserv = await create_payee(db_session, budget, "Northwind Payserv")

    for month in [*HISTORY, THIS_MONTH]:
        # Day 1 of the running month is today at the earliest, so never ahead.
        day = month if month == THIS_MONTH else month + timedelta(days=4)
        await create_transaction(
            db_session, budget, checking, "3000.00", day, payee=payserv, category=inflow
        )
        await create_transaction(db_session, budget, checking, "-1200.00", day, category=rent)
        await create_transaction(db_session, budget, checking, "-300.00", day, category=dining)
        await create_transaction(db_session, budget, checking, "-15.00", day, category=streaming)
    return budget


async def _all_time(db_session, budget) -> int:
    """What the range picker's "All time" asks for: every month the history
    touches, the running one included."""
    months = (await ReportService(db_session).available_range(budget.id, TODAY))["months_available"]
    assert months == 4  # three complete months and this one
    return months


@pytest.fixture(params=["all time", "twelve months"])
def ask(request):
    """Both settings: "All time", and the default twelve. Each asks for more
    complete months than a three-month-old history has."""

    async def months(db_session, budget) -> int:
        return await _all_time(db_session, budget) if request.param == "all time" else 12

    return months


class TestEveryAverageDividesByTheHistory:
    async def test_income_by_source_reads_the_paycheck_whole(self, db_session, ask):
        budget = await _young_household(db_session)
        data = await income_by_source(db_session, budget.id, await ask(db_session, budget), TODAY)

        # 9,000 over three months, not four (2,250.00).
        assert data["months"] == HISTORY
        assert data["months_averaged"] == 3
        assert data["avg_monthly"] == D("3000.00")

    async def test_cost_of_living_and_its_take_home(self, db_session, ask):
        budget = await _young_household(db_session)
        data = await cost_of_living(db_session, budget.id, await ask(db_session, budget), TODAY)

        assert data["months"] == HISTORY
        assert data["window_start"] == HISTORY[0]
        assert data["months_averaged"] == 3
        # Rent, not 900.00; the take-home it is held against, not 2,250.00.
        assert data["avg_monthly_cost_of_living"] == D("1200.00")
        assert data["avg_monthly_essentials"] == D("1200.00")
        assert data["avg_monthly_income"] == D("3000.00")
        (bills,) = data["groups"]
        assert bills["avg_monthly"] == D("1200.00")

    async def test_discretionary(self, db_session, ask):
        budget = await _young_household(db_session)
        data = await discretionary(
            ReportService(db_session), budget.id, await ask(db_session, budget), TODAY
        )

        assert data["months"] == HISTORY
        assert data["months_averaged"] == 3
        # Dining and streaming: 315.00 a month, not 236.25.
        assert data["avg_monthly"] == D("315.00")
        (fun,) = data["groups"]
        assert {c["category_name"]: c["avg_monthly"] for c in fun["categories"]} == {
            "Dining": D("300.00"),
            "Streaming": D("15.00"),
        }

    async def test_the_essentials_table(self, db_session, ask):
        budget = await _young_household(db_session)
        months = await ask(db_session, budget)
        data = await essentials_summary(db_session, budget.id, months, TODAY)

        assert data["months"] == months  # what was asked, still served
        assert data["window_start"] == HISTORY[0]
        assert data["months_averaged"] == 3
        assert [m["month"] for m in data["monthly_series"]] == HISTORY
        # It divided by the setting, not even by its window: 3,600 / 12 read
        # 300.00 on the default and 900.00 on "All time".
        assert data["monthly_total_average"] == D("1200.00")
        (rent,) = data["categories"]
        assert rent["monthly_average"] == D("1200.00")
        assert rent["months_with_spend"] == 3

    async def test_subscriptions_draw_no_month_before_the_history(self, db_session, ask):
        budget = await _young_household(db_session)
        data = await subscriptions_report(
            db_session, budget.id, await ask(db_session, budget), TODAY
        )

        # The chart's axis drew empty months nobody recorded.
        assert data["months"] == HISTORY
        (streaming,) = data["subscriptions"]
        assert streaming["monthly_amounts"] == [D("15")] * 3
        # A service younger than a year is projected from its cadence, on
        # either setting: the range picker moves the chart, never the cost.
        assert streaming["services"][0]["basis"] == "new"
        assert streaming["monthly"] == D("15.00")
        assert data["summary"]["total_annual"] == D("180.00")

    async def test_cost_of_living_quotes_the_essentials_table(self, db_session, ask):
        """The two reports read one window, so the Essentials figure on Cost of
        Living is the Essentials table's average, young budget or not."""
        budget = await _young_household(db_session)
        months = await ask(db_session, budget)
        col = await cost_of_living(db_session, budget.id, months, TODAY)
        ess = await essentials_summary(db_session, budget.id, months, TODAY)

        assert col["avg_monthly_essentials"] == ess["monthly_total_average"]
        assert (col["window_start"], col["window_end"]) == (
            ess["window_start"],
            ess["window_end"],
        )


class TestABudgetStartedThisMonth:
    """No complete month yet: nothing to average, and nothing invented."""

    async def test_every_average_is_empty_rather_than_zero_filled(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Bills")
        rent = await create_category(db_session, budget, group, "Rent")
        await tag_with_system_tags(db_session, rent, "essential")
        await create_transaction(db_session, budget, checking, "-1200.00", TODAY, category=rent)

        income = await income_by_source(db_session, budget.id, 12, TODAY)
        col = await cost_of_living(db_session, budget.id, 12, TODAY)
        ess = await essentials_summary(db_session, budget.id, 12, TODAY)

        assert income["months"] == col["months"] == []
        assert income["months_averaged"] == col["months_averaged"] == 0
        assert ess["months_averaged"] == 0 and ess["monthly_series"] == []
        assert income["avg_monthly"] == col["avg_monthly_cost_of_living"] == D("0")
        assert ess["monthly_total_average"] == D("0")
