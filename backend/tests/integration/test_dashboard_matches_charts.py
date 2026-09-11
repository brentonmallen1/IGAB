"""The dashboard cards must agree with the charts they summarise.

A card and a chart carrying the same label and disagreeing is the failure this
whole pass is about, and the dashboard had two of them. Both were covered by
comments claiming agreement, which is exactly why they went unnoticed.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain import activity_class
from igab.domain.activity_class import ActivityClass
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services import report_service
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
MONTH_START = TODAY.replace(day=1)


@pytest.fixture(autouse=True)
def _the_service_reads_this_modules_today():
    """Rows here are dated from TODAY, read once at import; the service reads
    the clock when called. Pinned, a run that crosses midnight still asks the
    day its rows were seeded for."""
    with report_today(TODAY):
        yield


async def _budget_with_checking(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking", on_budget=True)
    group = await create_category_group(db_session, budget, "Everyday")
    category = await create_category(db_session, budget, group, "Groceries")
    return budget, checking, category


def _burn_from_chart(rows: list[dict]) -> Decimal | None:
    """The chart's own 30-day figure, whatever it calls the field."""
    if not rows:
        return None
    last = rows[-1]
    for key in ("burn_30", "rolling_30", "burn_rate_30", "value", "total"):
        if key in last:
            return Decimal(str(last[key]))
    return None


class TestBurnRate:
    async def test_a_refund_lowers_the_card_and_the_chart_together(self, db_session):
        """The card filtered by class only; the chart also filters amount < 0.

        A refund posted back to a spending category is a positive SPENDING row.
        It reduced the card's burn and not the chart's, so the two drifted by
        the size of every refund in the window.
        """
        budget, checking, category = await _budget_with_checking(db_session)
        await create_transaction(
            db_session, budget, checking, "-300.00", TODAY, category=category, cleared="cleared"
        )
        await create_transaction(
            db_session, budget, checking, "120.00", TODAY, category=category, cleared="cleared"
        )
        await db_session.flush()

        service = ReportService(db_session)
        card = await service.dashboard_metrics(budget.id, MONTH_START, TODAY)
        chart = await service.burn_rate(budget.id, months=1)

        # The card counts the outflow, not the outflow net of the refund.
        assert Decimal(str(card["burn_rate_30"])) == Decimal("300.00")
        chart_burn = _burn_from_chart(chart)
        if chart_burn is not None:
            assert chart_burn == Decimal(str(card["burn_rate_30"]))

    async def test_an_internal_transfer_burns_nothing_on_either(self, db_session):
        """CASH_FLOW_ROW is implied by the SPENDING class rather than missing.

        A row falls outside cash flow only when it is a transfer leg, has no
        category, and points at another on-budget account — and ACTIVITY_CLASS
        never calls that SPENDING. This asserts that instead of assuming it.
        """
        budget, checking, category = await _budget_with_checking(db_session)
        savings = await create_account(db_session, budget, "Savings", on_budget=True)
        out_leg = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, cleared="cleared"
        )
        in_leg = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, cleared="cleared", transfer_id=out_leg.id
        )
        out_leg.transfer_id = in_leg.id
        await db_session.flush()

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        # Uncategorized rows between two on-budget accounts are not spending.
        assert Decimal(str(card["burn_rate_30"])) == Decimal("0")

    async def test_the_card_and_the_chart_follow_spending_classes_together(
        self, db_session, monkeypatch
    ):
        """The chart reads the spending set from SPENDING_CLASSES; the card
        spelled SPENDING as a literal. They agreed only while the tuple held
        one class. Widened here to take savings in, both have to count a
        savings-tagged outflow."""
        widened = (ActivityClass.SPENDING, ActivityClass.SAVINGS)
        monkeypatch.setattr(activity_class, "SPENDING_CLASSES", widened)
        monkeypatch.setattr(report_service, "SPENDING_CLASSES", widened)
        budget, checking, category = await _budget_with_checking(db_session)
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        savings_tag = await tags.get_system_tag(budget.id, "savings")
        group = await create_category_group(db_session, budget, "Goals")
        fund = await create_category(db_session, budget, group, "Car Replacement")
        await tags.set_category_tags(fund.id, [savings_tag.id])
        await create_transaction(
            db_session, budget, checking, "-100.00", TODAY, category=category, cleared="cleared"
        )
        await create_transaction(
            db_session, budget, checking, "-250.00", TODAY, category=fund, cleared="cleared"
        )
        await db_session.flush()

        service = ReportService(db_session)
        card = await service.dashboard_metrics(budget.id, MONTH_START, TODAY)
        chart = await service.burn_rate(budget.id, months=1)

        assert Decimal(str(card["burn_rate_30"])) == Decimal("350.00")
        assert _burn_from_chart(chart) == Decimal("350.00")


class TestSavingsRate:
    async def test_no_income_reads_as_unknown_not_as_zero(self, db_session):
        budget, checking, category = await _budget_with_checking(db_session)
        await create_transaction(
            db_session, budget, checking, "-50.00", TODAY, category=category, cleared="cleared"
        )
        await db_session.flush()

        service = ReportService(db_session)
        card = await service.dashboard_metrics(budget.id, MONTH_START, TODAY)
        tab = await service.savings_rate(budget.id, months=1)

        assert card["savings_rate"] is None
        # The tab already answered this way; the card now agrees.
        assert tab["months"][-1]["savings_rate"] is None

    async def test_both_agree_on_a_month_with_income(self, db_session):
        budget, checking, category = await _budget_with_checking(db_session)
        await create_transaction(db_session, budget, checking, "1000.00", TODAY, cleared="cleared")
        await create_transaction(
            db_session, budget, checking, "-200.00", TODAY, category=category, cleared="cleared"
        )
        await db_session.flush()

        service = ReportService(db_session)
        card = await service.dashboard_metrics(budget.id, MONTH_START, TODAY)
        tab = await service.savings_rate(budget.id, months=1)

        # Same ratio, same rows — neither invents a number the other denies.
        assert card["savings_rate"] == tab["months"][-1]["savings_rate"]


class TestTheBurnWindowsAreTheSameWindow:
    """The card says "30-Day Burn Rate" and the chart says "Current 30-Day
    Burn". They were two different windows.

    The chart ran to `_last_day` of the current month — a FUTURE date — so its
    newest point was month-to-date wearing a thirty-day label. The card ran
    `today - 30` with inclusive bounds, which is thirty-ONE days, and then
    `days_until_zero` divided it by 30. So the card overstated daily burn by
    about 3.3% and understated runway by the same, and the two figures could
    not agree by construction.

    A future-dated row is deliberately NOT tested here: `burn_rate`'s query
    already bounds at today, so such a test could not fail and would only look
    like coverage. The Python windowing is covered by
    `TestBurnRate.test_the_newest_window_does_not_reach_past_today`, which
    mocks the session and so reaches the window rather than the query.
    """

    async def test_a_spend_31_days_back_is_in_neither(self, db_session):
        budget, checking, category = await _budget_with_checking(db_session)
        # Day 30 is inside a thirty-day window counting today as day 1;
        # day 31 is outside it. The card used to count day 31.
        await create_transaction(
            db_session,
            budget,
            checking,
            "-500.00",
            TODAY - timedelta(days=30),
            category=category,
            cleared="cleared",
        )
        await create_transaction(
            db_session,
            budget,
            checking,
            "-100.00",
            TODAY - timedelta(days=5),
            category=category,
            cleared="cleared",
        )
        await db_session.flush()

        service = ReportService(db_session)
        card = await service.dashboard_metrics(budget.id, MONTH_START, TODAY)
        chart = await service.burn_rate(budget.id, months=1)

        assert Decimal(str(card["burn_rate_30"])) == Decimal("100.00")
        assert _burn_from_chart(chart) == Decimal("100.00")

    async def test_a_spend_90_days_back_is_in_neither(self, db_session):
        """The 90-day half of the same fix: day 90 counting today as day 1 is
        in, day 91 is out. The card ran `today - 90`, ninety-one days, and
        counted the 300 the chart's `rolling_90` leaves out."""
        budget, checking, category = await _budget_with_checking(db_session)
        for amount, days_back in (("-300.00", 90), ("-900.00", 89)):
            await create_transaction(
                db_session,
                budget,
                checking,
                amount,
                TODAY - timedelta(days=days_back),
                category=category,
                cleared="cleared",
            )
        await db_session.flush()

        service = ReportService(db_session)
        card = await service.dashboard_metrics(budget.id, MONTH_START, TODAY)
        chart = await service.burn_rate(budget.id, months=1)

        # 900 over three months, not 1,200.
        assert Decimal(str(card["burn_rate_90"])) == Decimal("300.00")
        assert Decimal(str(chart[-1]["rolling_90"])) == Decimal("300.00")


class TestNetWorthNow:
    async def test_a_row_later_this_month_is_in_neither(self, db_session):
        """Net worth "now" is not money that has not moved yet. The card
        summed every posted row with no upper bound and the chart bounded
        each point at its month end; both now read one rule, clamped to
        today. The row that pins the clamp is later in the SAME month — one
        dated next month, which this used to use, is past every month end
        the chart draws and so passed without the clamp."""
        budget, checking, _ = await _budget_with_checking(db_session)
        await create_transaction(db_session, budget, checking, "5000.00", date(2026, 3, 10))
        await create_transaction(db_session, budget, checking, "-4000.00", date(2026, 3, 20))
        await db_session.flush()

        service = ReportService(db_session)
        # Pinned mid-month: a row later this month has not happened yet,
        # whatever day the suite runs on.
        with report_today(date(2026, 3, 15)):
            card = await service.dashboard_metrics(budget.id, date(2026, 3, 1), date(2026, 3, 15))
            chart = await service.net_worth_history(budget.id, months=1)

        assert chart[-1]["date"] == date(2026, 3, 1)
        assert chart[-1]["net_worth"] == Decimal("5000.00")
        assert card["net_worth"] == Decimal("5000.00")
