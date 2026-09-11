"""The tools answer with the same figures the app shows.

The point of the tool layer is that the chat cannot disagree with the grid. So
these tests do not assert hand-written numbers; they assert the handler and the
service the UI uses return the *same* number. A tool that drifts fails here.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.ai.tools import handlers
from igab.ai.tools.context import ToolContext
from igab.guide.service import GuideService
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.snapshot_repo import SnapshotRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.budget_service import BudgetService
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
)

TODAY = date(2026, 9, 15)
MONTH = date(2026, 9, 1)


@pytest.fixture
async def ctx(db_session) -> ToolContext:
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    dining = await create_category(db_session, budget, group, "Dining")
    checking = await create_account(db_session, budget, "Harborstone Checking")

    await create_budget_assignment(db_session, budget, groceries, MONTH, Decimal("400.00"))
    await create_budget_assignment(db_session, budget, dining, MONTH, Decimal("150.00"))
    market = await create_payee(db_session, budget, "Cascade Market")
    cafe = await create_payee(db_session, budget, "Nordwind Cafe")
    await create_transaction(
        db_session, budget, checking, "-120.00", TODAY, category=groceries, payee=market
    )
    await create_transaction(
        db_session, budget, checking, "-45.00", TODAY, category=dining, payee=cafe
    )
    await db_session.flush()

    category_repo = CategoryRepository(db_session)
    account_repo = AccountRepository(db_session)
    transaction_repo = TransactionRepository(db_session)
    assignment_repo = BudgetAssignmentRepository(db_session)
    budgets = BudgetService(
        account_repo,
        category_repo,
        CategoryGroupRepository(db_session),
        assignment_repo,
        transaction_repo,
        snapshot_repo=SnapshotRepository(db_session),
    )
    reports = ReportService(db_session)
    return ToolContext(
        budget_id=budget.id,
        today=TODAY,
        session=db_session,
        reports=reports,
        budgets=budgets,
        guide=GuideService(db_session),
        categories=category_repo,
        accounts=account_repo,
        transactions=transaction_repo,
        payees=PayeeRepository(db_session),
    )


class TestTheFiguresMatchTheApp:
    async def test_budget_month_matches_the_summary_the_grid_reads(self, ctx):
        summary = await ctx.budgets.get_budget_summary(ctx.budget_id, MONTH)
        result = await handlers.get_budget_month(ctx, {"month": MONTH.isoformat()})
        assert result["ready_to_assign"] == float(summary.to_be_assigned)
        assert result["total_assigned"] == float(summary.total_assigned)
        assert result["overspent_count"] == summary.overspent_count

    async def test_budget_month_carries_the_name_and_whether_money_can_move_in(self, ctx):
        """The summary has neither; without the join the chat would advise
        moving money into an envelope that cannot take it."""
        result = await handlers.get_budget_month(ctx, {})
        everyday = next(g for g in result["groups"] if g["group"] == "Everyday")
        groceries = next(r for r in everyday["categories"] if r["category"] == "Groceries")
        # Only the unusual flag is spelled out; an ordinary envelope carries
        # neither, which halves the size of a large grid.
        assert "not_assignable" not in groceries
        assert groceries["assigned"] == 400.0

    async def test_spending_matches_the_report_the_charts_use(self, ctx):
        rows, total = await ctx.reports.spending_by_category(ctx.budget_id, MONTH, TODAY)
        result = await handlers.spending_by_category(
            ctx, {"start_date": MONTH.isoformat(), "end_date": TODAY.isoformat()}
        )
        assert result["total_amount"] == float(total)
        assert result["total_rows"] == len(rows)

    async def test_spending_says_what_it_counted(self, ctx):
        """The default excludes savings and debt principal, and a model that
        does not know will under-report where the money went."""
        default = await handlers.spending_by_category(
            ctx, {"start_date": MONTH.isoformat(), "end_date": TODAY.isoformat()}
        )
        assert "day-to-day" in default["covers"]
        fuller = await handlers.spending_by_category(
            ctx,
            {
                "start_date": MONTH.isoformat(),
                "end_date": TODAY.isoformat(),
                "include_savings": True,
            },
        )
        assert "debt principal" in fuller["covers"]

    async def test_budget_vs_actual_matches(self, ctx):
        data = await ctx.reports.budget_vs_actual(ctx.budget_id, MONTH, TODAY)
        result = await handlers.budget_vs_actual(
            ctx, {"start_date": MONTH.isoformat(), "end_date": TODAY.isoformat()}
        )
        assert result["total_assigned"] == float(data["total_assigned"])
        assert result["total_spent"] == float(data["total_spent"])

    async def test_search_reports_the_true_total_not_the_page(self, ctx):
        _, count, amount = await ctx.transactions.list_for_budget(ctx.budget_id, scope="leaf")
        result = await handlers.search_transactions(ctx, {})
        assert result["total_rows"] == count
        assert result["total_amount"] == float(amount)

    async def test_search_by_category_name_resolves_without_an_id(self, ctx):
        result = await handlers.search_transactions(ctx, {"category_name": "Groceries"})
        assert result["total_rows"] == 1
        assert result["rows"][0]["category"] == "Groceries"

    async def test_an_unmatched_category_returns_nothing_not_everything(self, ctx):
        """Falling back to "no filter" would answer a question nobody asked
        with the whole register."""
        result = await handlers.search_transactions(ctx, {"category_name": "Yacht Maintenance"})
        assert result["total_rows"] == 0
        assert "No envelope matches" in result["note"]

    async def test_data_range_is_reported_so_the_model_does_not_invent_history(self, ctx):
        result = await handlers.get_data_range(ctx, {})
        assert result["months_available"] >= 1
        assert result["earliest_month"] is not None

    async def test_list_categories_and_accounts(self, ctx):
        cats = await handlers.list_categories(ctx, {})
        assert {r["category"] if "category" in r else r["name"] for r in cats["rows"]} >= {
            "Groceries",
            "Dining",
        }
        accounts = await handlers.list_accounts(ctx, {})
        assert any(a["name"] == "Harborstone Checking" for a in accounts["rows"])

    async def test_income_vs_expense_and_savings_rate_run(self, ctx):
        assert "rows" in await handlers.income_vs_expense(ctx, {"months": 3})
        assert "summary" in await handlers.savings_rate(ctx, {"months": 3})

    async def test_payee_and_large_transactions_run(self, ctx):
        window = {"start_date": MONTH.isoformat(), "end_date": TODAY.isoformat()}
        payees = await handlers.payee_analysis(ctx, window)
        assert any(r["payee"] == "Cascade Market" for r in payees["rows"])
        # The service counts every payee in the window, and the handler passes
        # that count on: under the cap of 25 the ranking is the whole set.
        _, _, served_count, _ = await ctx.reports.payee_analysis(
            ctx.budget_id, MONTH, TODAY, limit=25
        )
        assert payees["total_rows"] == served_count == len(payees["rows"])
        assert payees["truncated"] is False
        assert "rows" in await handlers.large_transactions(ctx, window)

    async def test_months_argument_is_clamped(self, ctx):
        """The service methods take months with no validation of their own."""
        assert "rows" in await handlers.income_vs_expense(ctx, {"months": 100_000})
        assert "rows" in await handlers.income_vs_expense(ctx, {"months": -4})


class TestTheCheckupIsNotSecondGuessed:
    async def test_a_disabled_checkup_is_reported_as_disabled(self, ctx, monkeypatch):
        """Off means off. Empty findings rendered as "nothing wrong" would
        invent a clean bill of health nobody issued."""

        async def disabled(budget_id, *, stamp=False):
            return {"enabled": False, "metrics": [], "findings": []}

        monkeypatch.setattr(ctx.guide, "checkup", disabled)
        result = await handlers.guide_checkup(ctx, {})
        assert result["enabled"] is False
        assert "clean bill of health" in result["note"]

    async def test_the_checkup_is_never_stamped_by_a_tool(self, ctx, monkeypatch):
        """stamp=True writes "when did you last run your checkup". A question
        asked in the chat is not the user running their health report."""
        seen: dict = {}

        async def spy(budget_id, *, stamp=False):
            seen["stamp"] = stamp
            return {"enabled": True, "as_of": TODAY, "metrics": [], "findings": []}

        monkeypatch.setattr(ctx.guide, "checkup", spy)
        await handlers.guide_checkup(ctx, {})
        assert seen["stamp"] is False


class TestDatesAModelGotWrong:
    async def test_an_unparseable_date_falls_back_rather_than_failing(self, ctx):
        """Small models write "last month" here. The resolved value is
        recorded, so a wrong range shows up in the transparency view."""
        result = await handlers.spending_by_category(
            ctx, {"start_date": "last month", "end_date": "now"}
        )
        assert result["start_date"] == MONTH.isoformat()

    async def test_a_month_argument_is_snapped_to_the_first(self, ctx):
        result = await handlers.get_budget_month(ctx, {"month": "2026-09-22"})
        assert result["month"] == "2026-09-01"
