"""The Overview cards, against a real database.

They summarise the report tabs, so the property that matters most is not any
single figure but that they AGREE with the tab they summarise. They did not:
reading `amount < 0` as "expense" put "Savings Rate 0% / Expenses $5,000" on
the Overview beside a Savings Rate tab reading 40% and an Income vs Expenses
tab reading $3,000 — same window, same budget, two figures both labelled
savings rate.

Previously mocked at the session level, which could not test any of this: the
classification is a SQL CASE, so a mocked execute returns whatever the test
made up.
"""

from datetime import date, timedelta
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
MONTH_START = TODAY.replace(day=1)


async def _household(db_session, *, income="5000.00", spend="3000.00", to_brokerage="2000.00"):
    """A household earning, spending and saving in one month."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking", on_budget=True)
    brokerage = await create_account(
        db_session, budget, "Brokerage", account_type="investment", on_budget=False
    )
    inflow = await create_category_group(db_session, budget, "Inflow", is_system=True)
    rta = await create_category(db_session, budget, inflow, "Ready to Assign")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    investing = await create_category(db_session, budget, everyday, "Investing")

    await create_transaction(db_session, budget, checking, income, TODAY, category=rta)
    await create_transaction(db_session, budget, checking, f"-{spend}", TODAY, category=groceries)
    out = await create_transaction(
        db_session, budget, checking, f"-{to_brokerage}", TODAY, category=investing
    )
    into = await create_transaction(db_session, budget, brokerage, to_brokerage, TODAY)
    out.transfer_id, into.transfer_id = into.id, out.id
    await db_session.flush()
    return budget


class TestTheCardsAgreeWithTheTabs:
    async def test_savings_rate_matches_the_savings_rate_tab(self, db_session):
        budget = await _household(db_session)
        svc = ReportService(db_session)

        card = await svc.dashboard_metrics(budget.id, MONTH_START, TODAY)
        tab = await svc.savings_rate(budget.id, months=1)

        assert card["savings_rate"] == pytest.approx(tab["summary"]["savings_rate"])
        assert card["savings_rate"] == pytest.approx(0.4)

    async def test_expenses_match_income_vs_expenses(self, db_session):
        budget = await _household(db_session)
        svc = ReportService(db_session)

        card = await svc.dashboard_metrics(budget.id, MONTH_START, TODAY)
        months = await svc.income_vs_expense(budget.id, months=1)

        assert card["expenses_this_month"] == months[-1]["expenses"]
        assert card["expenses_this_month"] == Decimal("3000.00")

    async def test_income_matches_income_vs_expenses(self, db_session):
        budget = await _household(db_session)
        svc = ReportService(db_session)

        card = await svc.dashboard_metrics(budget.id, MONTH_START, TODAY)
        months = await svc.income_vs_expense(budget.id, months=1)

        assert card["income_this_month"] == months[-1]["income"] == Decimal("5000.00")

    async def test_burn_rate_matches_the_burn_rate_chart(self, db_session):
        budget = await _household(db_session)
        svc = ReportService(db_session)

        card = await svc.dashboard_metrics(budget.id, MONTH_START, TODAY)
        points = await svc.burn_rate(budget.id, months=1)

        assert card["burn_rate_30"] == points[-1]["rolling_30"]

    async def test_saving_is_not_reported_as_spending(self, db_session):
        """The whole point: $2,000 to a brokerage is not $2,000 spent."""
        budget = await _household(db_session)
        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)
        assert card["expenses_this_month"] == Decimal("3000.00")
        assert card["burn_rate_30"] == Decimal("3000.00")


class TestFiguresPreservedFromTheOldSuite:
    async def test_no_transactions_yields_zeros(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)
        assert card["net_worth"] == Decimal("0")
        assert card["top_categories"] == []
        assert card["savings_rate"] == 0.0

    async def test_net_worth_spans_every_account(self, db_session):
        """Off-budget scopes envelope math, never the balance sheet."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        await create_transaction(db_session, budget, checking, "2000.00", TODAY)
        await create_transaction(db_session, budget, brokerage, "500.00", TODAY)
        await db_session.flush()

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        assert card["net_worth"] == Decimal("2500.00")

    async def test_tracked_account_activity_is_not_income(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        await create_transaction(db_session, budget, brokerage, "800.00", TODAY)
        await db_session.flush()

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        assert card["income_this_month"] == Decimal("0"), "market growth is not income"

    async def test_internal_transfers_touch_neither_side(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        savings = await create_account(db_session, budget, "Savings", on_budget=True)
        out = await create_transaction(db_session, budget, checking, "-400.00", TODAY)
        into = await create_transaction(db_session, budget, savings, "400.00", TODAY)
        out.transfer_id, into.transfer_id = into.id, out.id
        await db_session.flush()

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        assert card["income_this_month"] == Decimal("0")
        assert card["expenses_this_month"] == Decimal("0")

    async def test_savings_rate_is_zero_without_income(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        group = await create_category_group(db_session, budget, "Everyday")
        cat = await create_category(db_session, budget, group, "Groceries")
        await create_transaction(db_session, budget, checking, "-50.00", TODAY, category=cat)
        await db_session.flush()

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        assert card["savings_rate"] == 0.0

    async def test_top_categories_sorted_by_spending(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        group = await create_category_group(db_session, budget, "Everyday")
        for name, amount in (("Rent", "-1200.00"), ("Groceries", "-300.00"), ("Fun", "-90.00")):
            cat = await create_category(db_session, budget, group, name)
            await create_transaction(db_session, budget, checking, amount, TODAY, category=cat)
        await db_session.flush()

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        assert [c["name"] for c in card["top_categories"]] == ["Rent", "Groceries", "Fun"]

    async def test_days_until_zero_uses_the_burn_rate(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        group = await create_category_group(db_session, budget, "Everyday")
        cat = await create_category(db_session, budget, group, "Groceries")
        await create_transaction(db_session, budget, checking, "3000.00", TODAY - timedelta(days=5))
        await create_transaction(db_session, budget, checking, "-300.00", TODAY, category=cat)
        await db_session.flush()

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        assert card["days_until_zero"] == pytest.approx(float(card["net_worth"]) / (300 / 30))

    async def test_days_until_zero_is_none_without_burn(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        await create_transaction(db_session, budget, checking, "3000.00", TODAY)
        await db_session.flush()

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        assert card["days_until_zero"] is None
