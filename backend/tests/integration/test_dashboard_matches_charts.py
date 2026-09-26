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
from igab.services.report_service import ReportService
from tests.report_clock import report_today

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
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
        """A refund posted back to a spending category is a positive SPENDING
        row. The card once netted it and the chart did not; then both were
        made to ignore it (`amount < 0`), so the burn stood $120 above what
        Spent This Period and Essentials read for the same rows. Both net it
        now, in the prior window too."""
        budget, checking, category = await _budget_with_checking(db_session)
        for amount, days_back in (("-300.00", 0), ("120.00", 0), ("-500.00", 40), ("100.00", 35)):
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

        assert card["burn_rate_30"] == chart[-1]["rolling_30"] == Decimal("180.00")
        # 400 net over the prior sixty days is 200 per thirty.
        assert card["burn_rate_prior_60"] == chart[-1]["prior_60"] == Decimal("200.00")
        # And the refund lowers Spent This Period by the same rule.
        assert card["expenses_this_month"] == Decimal("180.00")

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

        service = ReportService(db_session)
        card = await service.dashboard_metrics(budget.id, MONTH_START, TODAY)
        chart = await service.burn_rate(budget.id, months=1)

        # Uncategorized rows between two on-budget accounts are not spending —
        # and the chart, which now reads the same rows without CASH_FLOW_ROW or
        # a sign filter, does not net the +500 leg against anything either.
        assert card["burn_rate_30"] == chart[-1]["rolling_30"] == Decimal("0")

    async def test_the_card_and_the_chart_follow_spending_classes_together(
        self, db_session, monkeypatch
    ):
        """The chart reads the spending set from SPENDING_CLASSES; the card
        spelled SPENDING as a literal. They agreed only while the tuple held
        one class. Widened here to take savings in, both have to count a
        savings-tagged outflow."""
        widened = (ActivityClass.SPENDING, ActivityClass.SAVINGS)
        monkeypatch.setattr(activity_class, "SPENDING_CLASSES", widened)
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


class TestDebtPayments:
    async def test_the_card_and_both_debt_series_count_the_same_payment(self, db_session):
        """The means verdict's debt payments are served by the dashboard; the
        Savings Rate tab and Income vs Expenses already draw `debt_principal`.
        Three readers of one class over one window, so one figure."""
        budget, checking, category = await _budget_with_checking(db_session)
        loan = await create_account(
            db_session, budget, "Harborstone Mortgage", account_type="mortgage", on_budget=False
        )
        housing = await create_category_group(db_session, budget, "Housing")
        mortgage = await create_category(db_session, budget, housing, "Mortgage")
        await create_transaction(db_session, budget, checking, "4000.00", TODAY, cleared="cleared")
        await create_transaction(
            db_session, budget, checking, "-600.00", TODAY, category=category, cleared="cleared"
        )
        await create_transfer(
            db_session, budget, checking, loan, "1500.00", TODAY, category=mortgage
        )
        await create_transfer(db_session, budget, checking, loan, "250.00", TODAY)
        await db_session.flush()

        service = ReportService(db_session)
        card = await service.dashboard_metrics(budget.id, MONTH_START, TODAY)
        rate = await service.savings_rate(budget.id, months=1)
        flows = await service.income_vs_expense(budget.id, months=1)

        assert card["debt_payments_this_month"] == Decimal("1750.00")
        assert rate["months"][-1]["debt_principal"] == card["debt_payments_this_month"]
        assert flows[-1]["debt_principal"] == card["debt_payments_this_month"]
        # And what living cost is the chart's spending plus its debt principal.
        assert card["outflows_this_month"] == flows[-1]["expenses"] + flows[-1]["debt_principal"]


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
        """The far edge of the same fix: day 90 counting today as day 1 is the
        prior window's oldest day, day 91 is outside it. The card once ran
        `today - 90`, ninety-one days, and counted a row the chart left out."""
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

        # 900 over the prior sixty days, per thirty — not 1,200.
        assert card["burn_rate_prior_60"] == chart[-1]["prior_60"] == Decimal("450.00")


class TestBurnAgainstThePriorSixtyDays:
    """The Overview's sub-line and the Burn Rate chart's second series used to
    be the last ninety days ÷ 3, which contains the thirty days it was held
    against: steady spending with a spike read as two nearly equal figures,
    because the spike was in both. The comparison is now the sixty days before
    the thirty, per thirty days, and the card and the chart's newest point are
    one computation."""

    async def _steady_then_a_spike(self, db_session, budget, checking, category):
        # Steady: $300 twice a month, back through the prior sixty days.
        for days_back in (10, 25, 40, 55, 70, 85):
            await create_transaction(
                db_session,
                budget,
                checking,
                "-300.00",
                TODAY - timedelta(days=days_back),
                category=category,
                cleared="cleared",
            )
        # A spike inside the last thirty: one more $300 bill.
        await create_transaction(
            db_session,
            budget,
            checking,
            "-300.00",
            TODAY - timedelta(days=3),
            category=category,
            cleared="cleared",
        )
        await db_session.flush()

    async def test_the_card_and_the_newest_point_show_the_spike(self, db_session):
        budget, checking, category = await _budget_with_checking(db_session)
        await self._steady_then_a_spike(db_session, budget, checking, category)

        service = ReportService(db_session)
        card = await service.dashboard_metrics(budget.id, MONTH_START, TODAY)
        chart = await service.burn_rate(budget.id, months=3)

        recent, prior = card["burn_rate_30"], card["burn_rate_prior_60"]
        assert recent == Decimal("900.00")
        assert prior == Decimal("600.00")
        # +50%: the client composes it from these two served figures.
        assert (recent - prior) / prior == Decimal("0.5")
        # The old ninety-day average read 700 here, spike included — +29%.
        assert (chart[-1]["rolling_30"], chart[-1]["prior_60"]) == (recent, prior)
        assert chart[-1]["date"] == MONTH_START


class TestTheReadersToday:
    """Both figures end "today", and the browser's today is not the server's
    near midnight. Seeded one day past the server's clock, a charge dated the
    reader's today is in the thirty days only when the reader's date is sent,
    and a charge on the server's day 30 has moved to the reader's prior sixty."""

    async def test_client_today_moves_both_windows(self, api_client, db_session):
        user = api_client.test_user
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        group = await create_category_group(db_session, budget, "Everyday")
        category = await create_category(db_session, budget, group, "Groceries")
        tomorrow = TODAY + timedelta(days=1)
        await create_transaction(
            db_session, budget, checking, "-250.00", tomorrow, category=category, cleared="cleared"
        )
        # Day 30 for the server, still recent; day 31, the prior window's
        # newest, for the reader.
        await create_transaction(
            db_session,
            budget,
            checking,
            "-600.00",
            TODAY - timedelta(days=29),
            category=category,
            cleared="cleared",
        )
        await db_session.flush()
        base = f"/api/v1/{budget.id}/reports"

        server = (await api_client.get(f"{base}/dashboard")).json()
        reader = (
            await api_client.get(f"{base}/dashboard", params={"client_today": tomorrow.isoformat()})
        ).json()
        chart = (
            await api_client.get(
                f"{base}/burn-rate", params={"months": 1, "client_today": tomorrow.isoformat()}
            )
        ).json()["points"]

        assert Decimal(str(server["burn_rate_30"])) == Decimal("600.00")
        assert Decimal(str(server["burn_rate_prior_60"])) == Decimal("0")
        assert Decimal(str(reader["burn_rate_30"])) == Decimal("250.00")
        assert Decimal(str(reader["burn_rate_prior_60"])) == Decimal("300.00")
        assert Decimal(str(chart[-1]["rolling_30"])) == Decimal("250.00")
        assert Decimal(str(chart[-1]["prior_60"])) == Decimal("300.00")
        assert chart[-1]["date"] == tomorrow.replace(day=1).isoformat()


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
