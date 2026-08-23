"""The dashboard cards must agree with the charts they summarise.

A card and a chart carrying the same label and disagreeing is the failure this
whole pass is about, and the dashboard had two of them. Both were covered by
comments claiming agreement, which is exactly why they went unnoticed.
"""

from datetime import date, timedelta
from decimal import Decimal

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
MONTH_START = TODAY.replace(day=1)


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
        await create_transaction(
            db_session, budget, checking, "1000.00", TODAY, cleared="cleared"
        )
        await create_transaction(
            db_session, budget, checking, "-200.00", TODAY, category=category, cleared="cleared"
        )
        await db_session.flush()

        service = ReportService(db_session)
        card = await service.dashboard_metrics(budget.id, MONTH_START, TODAY)
        tab = await service.savings_rate(budget.id, months=1)

        # Same ratio, same rows — neither invents a number the other denies.
        assert card["savings_rate"] == tab["months"][-1]["savings_rate"]
