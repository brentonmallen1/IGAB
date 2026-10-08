"""The tools answer with the same figures the app shows.

The point of the tool layer is that the chat cannot disagree with the grid. So
these tests do not assert hand-written numbers; they assert the handler and the
service the UI uses return the *same* number. A tool that drifts fails here.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.ai.tools import handlers
from igab.ai.tools.context import ToolContext, build_tool_context
from igab.domain.spending import OFF_BUDGET_LABEL, UNCATEGORIZED
from igab.repositories.txn_query import DEFAULT_GROUPS, MAX_GROUPS

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_transfer,
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

    # The real builder, not a second copy of its wiring: this fixture used to
    # construct every service by hand, so adding one to the context broke
    # seventeen tests that did not care about it. `build_tool_context` is the
    # one list, and its own docstring says why there must not be two.
    return await build_tool_context(db_session, budget.id, TODAY)


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
        assert "debt payments" in fuller["covers"]

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

    async def test_an_unmatched_payee_returns_nothing_not_everything(self, ctx):
        """The payee half of the same promise. The handler passed [] and the
        listing read an empty list as no filter, so the note said nothing was
        searched above every row in the budget."""
        result = await handlers.search_transactions(ctx, {"payee_name": "Yacht Club"})
        assert result["total_rows"] == 0
        assert "No payee matches" in result["note"]

    async def test_an_unmatched_account_returns_nothing_not_everything(self, ctx):
        """The account half of the same promise: the handler passed [] and
        the listing read an empty list as no filter."""
        result = await handlers.search_transactions(ctx, {"account_name": "Tidewater Savings"})
        assert result["total_rows"] == 0
        assert "No account matches" in result["note"]
        rolled = await handlers.query_transactions(
            ctx, {"account_name": "Tidewater Savings", "group_by": "category"}
        )
        assert (rolled["groups"], rolled["group_count"]) == ([], 0)

    async def test_budget_vs_actual_states_the_headline_the_rows_sum_to(self, ctx):
        data = await ctx.reports.budget_vs_actual(ctx.budget_id, MONTH, TODAY)
        result = await handlers.budget_vs_actual(
            ctx, {"start_date": MONTH.isoformat(), "end_date": TODAY.isoformat()}
        )
        # The headline is the rows summed, figure by figure — the assistant can
        # never quote a total the rows beneath it do not add up to.
        for key in ("funded", "spent", "left", "overspent"):
            rows = sum(c[key] for c in data["categories"])
            assert result[f"total_{key}"] == float(rows), key

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
        served_count = (await ctx.reports.payee_analysis(ctx.budget_id, MONTH, TODAY, limit=25))[
            "payee_count"
        ]
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

        async def disabled(budget_id, *, stamp=False, today=None):
            return {"enabled": False, "metrics": [], "findings": []}

        monkeypatch.setattr(ctx.guide, "checkup", disabled)
        result = await handlers.guide_checkup(ctx, {})
        assert result["enabled"] is False
        assert "clean bill of health" in result["note"]

    async def test_the_checkup_is_never_stamped_by_a_tool(self, ctx, monkeypatch):
        """stamp=True writes "when did you last run your checkup". A question
        asked in the chat is not the user running their health report."""
        seen: dict = {}

        async def spy(budget_id, *, stamp=False, today=None):
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


AUGUST = {"start_date": "2026-08-01", "end_date": "2026-08-31"}


@pytest.fixture
async def busy_month(db_session) -> ToolContext:
    """The tester's August, invented and rescaled.

    Income of 20,000 into Ready to Assign; a 1,500 mortgage payment from
    checking to an off-budget loan, filed under Mortgage; sixty envelopes
    spending 10, 20 … 600 (18,300 in all); a 500 move to an on-budget HYSA;
    and a +40,000 market adjustment on an off-budget brokerage — twice the
    month's income, which the old rollup ranked first as "Uncategorized".

    62 groups by default: Ready to Assign, Mortgage and the sixty envelopes.
    The default 50 keep the twelve smallest envelopes (10 … 120, -780 in all)
    out.
    """
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    inflow_group = await create_category_group(db_session, budget, "Inflow", is_system=True)
    ready = await create_category(db_session, budget, inflow_group, "Inflow: Ready to Assign")
    bills = await create_category_group(db_session, budget, "Bills")
    mortgage = await create_category(db_session, budget, bills, "Mortgage")
    everyday = await create_category_group(db_session, budget, "Everyday")
    checking = await create_account(db_session, budget, "Harborstone Checking")
    hysa = await create_account(db_session, budget, "Cascade Point HYSA", account_type="savings")
    brokerage = await create_account(
        db_session, budget, "Northwind Brokerage", account_type="investment", on_budget=False
    )
    loan = await create_account(
        db_session, budget, "Harborstone Mortgage", account_type="mortgage", on_budget=False
    )
    payroll = await create_payee(db_session, budget, "Northwind Payserv")

    when = date(2026, 8, 14)
    await create_transaction(
        db_session, budget, checking, "20000", when, category=ready, payee=payroll
    )
    await create_transfer(db_session, budget, checking, loan, "1500", when, category=mortgage)
    await create_transfer(db_session, budget, checking, hysa, "500", when)
    await create_transaction(db_session, budget, brokerage, "40000", when)
    for i in range(1, 61):
        envelope = await create_category(db_session, budget, everyday, f"Envelope {i:02d}")
        await create_transaction(
            db_session, budget, checking, Decimal(-10 * i), when, category=envelope
        )
    await db_session.flush()
    return await build_tool_context(db_session, budget.id, TODAY)


class TestWhereDidMyMoneyGo:
    """`query_transactions` asked where a month went, with no limit.

    It ranked a positive "Uncategorized" (a tracking account's market
    adjustment) first, income second, then the smallest spends — the largest
    ones were cut — and said only "The top 25 of 34 groups."
    """

    async def test_tracking_account_rows_are_not_spending(self, busy_month):
        result = await handlers.query_transactions(busy_month, {**AUGUST})
        names = {g["group"] for g in result["groups"]}
        assert OFF_BUDGET_LABEL not in names
        assert not any(g["group"] == UNCATEGORIZED and g["value"] > 0 for g in result["groups"])
        # Income, less the mortgage and the sixty envelopes; no 40,000.
        assert result["total"] == 200.0

    async def test_the_largest_spends_are_the_ones_shown(self, busy_month):
        result = await handlers.query_transactions(busy_month, {**AUGUST})
        groups = [g["group"] for g in result["groups"]]
        assert len(groups) == DEFAULT_GROUPS
        assert groups[:3] == ["Inflow: Ready to Assign", "Mortgage", "Envelope 60"]
        assert "Envelope 13" in groups
        assert "Envelope 12" not in groups

    async def test_the_cut_is_stated_truthfully(self, busy_month):
        result = await handlers.query_transactions(busy_month, {**AUGUST})
        assert result["group_count"] == 62
        assert result["truncated"] is True
        assert (result["omitted_groups"], result["omitted_value"]) == (12, -780.0)
        assert "Ranked by size, largest first." in result["note"]
        assert "Showing 50 of 62 groups; the other 12 total -780.00." in result["note"]
        assert f"up to {MAX_GROUPS}" in result["note"]
        assert "left out" in result["note"]

    async def test_a_higher_limit_shows_everything(self, busy_month):
        result = await handlers.query_transactions(busy_month, {**AUGUST, "limit": MAX_GROUPS})
        assert (len(result["groups"]), result["truncated"], result["omitted_groups"]) == (
            62,
            False,
            0,
        )
        assert "Showing" not in result["note"]

    async def test_mixed_signs_are_called_out(self, busy_month):
        mixed = await handlers.query_transactions(busy_month, {**AUGUST})
        assert "mix both" in mixed["note"]
        outflows = await handlers.query_transactions(busy_month, {**AUGUST, "direction": "outflow"})
        assert "mix both" not in outflows["note"]

    async def test_an_average_says_only_how_many_were_cut(self, busy_month):
        result = await handlers.query_transactions(busy_month, {**AUGUST, "aggregate": "avg"})
        assert result["omitted_groups"] == 12
        assert "total" not in result and "omitted_value" not in result
        assert "12 more were left out" in result["note"]

    async def test_naming_the_tracking_account_brings_its_rows_back(self, busy_month):
        result = await handlers.query_transactions(
            busy_month, {**AUGUST, "account_name": "Northwind Brokerage"}
        )
        assert [(g["group"], g["value"]) for g in result["groups"]] == [(OFF_BUDGET_LABEL, 40000.0)]
        assert result["covers"] == "every row on the named account"

    async def test_is_transfer_asks_for_transfers_on_budget_accounts(self, busy_month):
        result = await handlers.query_transactions(
            busy_month, {**AUGUST, "is_transfer": True, "group_by": "account"}
        )
        # The mortgage's checking leg and both legs of the HYSA move; the
        # loan's own leg is on a tracking account.
        assert {g["group"]: g["value"] for g in result["groups"]} == {
            "Harborstone Checking": -2000.0,
            "Cascade Point HYSA": 500.0,
        }

    async def test_unmatched_names_add_their_notes_rather_than_replace(self, busy_month):
        result = await handlers.query_transactions(
            busy_month, {"category_name": "Yacht Maintenance", "payee_name": "Yacht Club"}
        )
        assert "No envelope matches" in result["note"]
        assert "No payee matches" in result["note"]

    async def test_search_covers_the_same_rows_by_default(self, busy_month):
        """The listing and the rollup share `_filters_from_args`, so the
        default scope is the same on both."""
        listed = await handlers.search_transactions(busy_month, {**AUGUST})
        rolled = await handlers.query_transactions(busy_month, {**AUGUST, "limit": MAX_GROUPS})
        assert listed["total_rows"] == sum(g["rows"] for g in rolled["groups"]) == 62
        assert listed["total_amount"] == rolled["total"] == 200.0
        assert listed["covers"] == rolled["covers"] == handlers.DEFAULT_SCOPE
