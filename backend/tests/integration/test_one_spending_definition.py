"""One meaning of "spending" across every report of that shape.

The same twelve months read four ways before this: the Breakdown and Spending
Trends counted categorized outflows only; Payees and Day Patterns counted
uncategorized outflows too; Income vs Expenses and Burn Rate netted refunds;
Seasonality counted every class. A month of $6,300 net spending read $10,400
on Trends.

Now there is one row set (`txn_filters.SPENDING_ROW`, read through
`ReportService._spending_query`): net of refunds, with uncategorized spending
as its own line. Each test below is a divergence one of those reports used to
have, named for the report that got it wrong.

Amounts are round and invented; dates are pinned so the complete-month
arithmetic is checkable on paper. 18 March 2026 is "today": January and
February are complete, March is running.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.services.report_basics import spending_trends
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_transfer,
    money,
)

TODAY = date(2026, 3, 18)
JAN, FEB, MAR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)
WINDOW = (JAN, TODAY)


async def _household(db_session, api_client):
    """January: groceries 300 less a 50 refund, 40 uncategorized, and a 500
    transfer into a tracked savings account. February: dining 120, and a 90
    return to Shopping that bought nothing this month — a category that nets
    negative. March so far: groceries 200."""
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    hysa = await create_account(
        db_session,
        budget,
        "Cascade Point HYSA",
        account_type="savings",
        on_budget=False,
        counts_as_savings=True,
    )
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    dining = await create_category(db_session, budget, everyday, "Dining")
    shopping = await create_category(db_session, budget, everyday, "Shopping")
    market = await create_payee(db_session, budget, "Corner Market")
    shop = await create_payee(db_session, budget, "Alder Street Goods")

    async def row(amount, when, category=None, payee=None):
        await create_transaction(
            db_session, budget, checking, amount, when, category=category, payee=payee
        )

    await row("-300.00", date(2026, 1, 10), groceries, market)
    await row("50.00", date(2026, 1, 20), groceries, market)
    await row("-40.00", date(2026, 1, 12), payee=shop)
    await create_transfer(db_session, budget, checking, hysa, "500.00", date(2026, 1, 25))
    await row("-120.00", date(2026, 2, 7), dining, shop)
    await row("90.00", date(2026, 2, 14), shopping, shop)
    await row("-200.00", date(2026, 3, 9), groceries, market)
    await db_session.commit()
    return budget, {"groceries": groceries, "dining": dining, "shopping": shopping}


#: January 250 + 40, February 120 - 90, March 200.
SPENT = Decimal("520.00")


async def _get(api_client, budget, report, **params):
    r = await api_client.get(
        f"/api/v1/{budget.id}/reports/{report}",
        params={"client_today": TODAY.isoformat(), **params},
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestEveryReportTotalsTheSameSpending:
    async def test_all_seven_agree_with_income_vs_expenses(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        svc = ReportService(db_session)
        _cats, by_category = await svc.spending_by_category(budget.id, *WINDOW)
        _items, grouped, _notes = await svc.spending_grouped(budget.id, *WINDOW)
        trends = await spending_trends(svc, budget.id, *WINDOW, today=TODAY)
        days = await svc.day_patterns(budget.id, *WINDOW, today=TODAY)
        by_day = sum((d["total"] for d in days["days"]), Decimal("0"))
        payees = (await svc.payee_analysis(budget.id, *WINDOW))["total"]
        expenses = await svc.income_vs_expense(budget.id, 3, TODAY)

        assert by_category == grouped == trends["total"] == by_day == SPENT
        # Every January row has a payee but the uncategorized 40 has one too,
        # so nothing here is payee-less and Payees matches the rest.
        assert payees == SPENT
        # And month by month, the Expenses bar is the Trends column.
        assert [m["expenses"] for m in expenses] == trends["monthly_totals"]

    async def test_payees_leave_out_only_rows_with_no_payee(self, db_session, api_client):
        """The one stated gap: a row with no payee of record has no shop to
        rank under. Payees fall short of the Breakdown by exactly that."""
        budget, cats = await _household(db_session, api_client)
        checking = await create_account(db_session, budget, "Second Checking")
        await create_transaction(
            db_session, budget, checking, "-35.00", date(2026, 2, 3), category=cats["dining"]
        )
        await db_session.commit()
        svc = ReportService(db_session)
        _cats, breakdown = await svc.spending_by_category(budget.id, *WINDOW)
        payees = (await svc.payee_analysis(budget.id, *WINDOW))["total"]
        assert breakdown - payees == Decimal("35.00")


class TestRefundsAreNetted:
    async def test_trends_used_to_be_gross(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "spending-trends", start_date=JAN.isoformat(), end_date="2026-03-18"
        )
        groceries = next(s for s in body["series"] if s["name"] == "Groceries")
        # 300 - 50 in January; the refund was invisible and it read 300.
        assert money(groceries["monthly"][0]) == Decimal("250.00")

    async def test_the_breakdown_used_to_be_gross(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "spending-grouped", start_date="2026-01-01", end_date="2026-01-31"
        )
        by_name = {g["name"]: money(g["total"]) for g in body["groups"]}
        assert by_name["Groceries"] == Decimal("250.00")

    async def test_payees_used_to_be_gross(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "payee-analysis", start_date="2026-01-01", end_date="2026-01-31"
        )
        by_name = {p["payee_name"]: money(p["total"]) for p in body["payees"]}
        assert by_name["Corner Market"] == Decimal("250.00")

    async def test_day_patterns_used_to_be_gross(self, db_session, api_client):
        """The refund posted on a Tuesday, the purchase on a Saturday; each
        day carries its own row, so Tuesday goes negative."""
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "day-patterns", start_date="2026-01-01", end_date="2026-01-31"
        )
        by_day = {d["day_name"]: money(d["total"]) for d in body["days"]}
        assert by_day["Tuesday"] == Decimal("-50.00")
        assert by_day["Saturday"] == Decimal("300.00")

    async def test_seasonality_used_to_be_gross(self, db_session, api_client):
        budget, cats = await _household(db_session, api_client)
        body = await _get(api_client, budget, "seasonality", months=2)
        cell = next(
            c
            for c in body["cells"]
            if c["category_id"] == str(cats["groceries"].id) and c["month"] == "2026-01-01"
        )
        assert money(cell["total"]) == Decimal("250.00")


class TestACategoryThatNetsNegativeIsShownSigned:
    """Shopping took a 90 return in February and bought nothing: -90. It is
    listed, signed, and the total above it includes it — a list that hid it
    would not add up to that total."""

    async def test_on_the_breakdown(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        items, total, _ = await ReportService(db_session).spending_grouped(
            budget.id, FEB, date(2026, 2, 28)
        )
        by_name = {i["name"]: i for i in items}
        assert by_name["Shopping"]["total"] == Decimal("-90.00")
        assert total == Decimal("30.00")
        # Sorted last, and its share is signed rather than dropped.
        assert items[-1]["name"] == "Shopping"
        assert by_name["Shopping"]["pct"] == pytest.approx(-300.0)

    async def test_on_trends_and_seasonality(self, db_session, api_client):
        budget, cats = await _household(db_session, api_client)
        svc = ReportService(db_session)
        trends = await spending_trends(svc, budget.id, *WINDOW, today=TODAY)
        shopping = next(s for s in trends["series"] if s["name"] == "Shopping")
        assert shopping["monthly"] == [Decimal("0"), Decimal("-90.00"), Decimal("0")]
        grid = await svc.seasonality(budget.id, 2, TODAY)
        (cell,) = [c for c in grid["cells"] if c["category_id"] == cats["shopping"].id]
        assert cell["total"] == Decimal("-90.00")

    async def test_with_no_positive_total_every_share_is_zero(self, db_session, api_client):
        """A window of nothing but a refund: no share of a non-positive total
        is stated, rather than a -100% nobody could read."""
        budget, _ = await _household(db_session, api_client)
        items, total, _ = await ReportService(db_session).spending_grouped(
            budget.id, date(2026, 2, 10), date(2026, 2, 20)
        )
        assert total == Decimal("-90.00")
        assert [i["pct"] for i in items] == [0.0]


class TestUncategorizedIsItsOwnLine:
    async def test_the_breakdown_used_to_omit_uncategorized(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "spending-grouped", start_date="2026-01-01", end_date="2026-01-31"
        )
        (line,) = [g for g in body["groups"] if g["id"] is None]
        assert (line["name"], line["parent_id"], line["parent_name"]) == (
            "Uncategorized",
            None,
            "Uncategorized",
        )
        assert money(line["total"]) == Decimal("40.00")
        assert money(body["total"]) == Decimal("290.00")

    async def test_trends_used_to_omit_uncategorized(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        trends = await spending_trends(ReportService(db_session), budget.id, *WINDOW, today=TODAY)
        (line,) = [s for s in trends["series"] if s["id"] is None]
        assert line["name"] == line["group_name"] == "Uncategorized"
        assert line["monthly"][0] == Decimal("40.00")

    async def test_seasonality_used_to_omit_uncategorized(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        grid = await ReportService(db_session).seasonality(budget.id, 2, TODAY)
        assert {"id": None, "name": "Uncategorized"} in grid["categories"]

    async def test_the_top_spending_card_names_it(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        cats, _ = await ReportService(db_session).spending_by_category(
            budget.id, date(2026, 1, 1), date(2026, 1, 31)
        )
        assert [(c["name"], c["group_name"], c["total"]) for c in cats] == [
            ("Groceries", "Everyday", Decimal("250.00")),
            ("Uncategorized", "Uncategorized", Decimal("40.00")),
        ]

    async def test_a_category_scope_leaves_it_out(self, db_session, api_client):
        """Picking categories is asking about those categories; uncategorized
        spending is in none of them."""
        budget, cats = await _household(db_session, api_client)
        items, total, _ = await ReportService(db_session).spending_grouped(
            budget.id, *WINDOW, category_ids=[cats["groceries"].id]
        )
        assert [i["name"] for i in items] == ["Groceries"]
        assert total == Decimal("450.00")


class TestSeasonalityCountsTheSpendingClasses:
    async def test_seasonality_used_to_count_every_class(self, db_session, api_client):
        """The 500 moved to savings in January coloured the grid as spending.
        It is left out unless the reader includes savings, as on every other
        spending report."""
        budget, _ = await _household(db_session, api_client)
        default = await _get(api_client, budget, "seasonality", months=2)
        assert sum(money(c["total"]) for c in default["cells"]) == Decimal("320.00")
        assert default["counted_classes"] == ["spending"]

        widened = await _get(api_client, budget, "seasonality", months=2, include_savings="true")
        assert sum(money(c["total"]) for c in widened["cells"]) == Decimal("820.00")
        assert widened["counted_classes"] == ["debt_principal", "savings", "spending"]

    async def test_it_says_how_many_categories_it_cut_from(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        body = await _get(api_client, budget, "seasonality", months=2)
        assert body["category_count"] == 4
        assert len(body["categories"]) == 4


class TestDrillsTotalWhatChartsTotal:
    """`spendingDrillClasses` was a client copy of the class set, and every
    spending drill also sent `direction: outflow` — so a refund in a bar was
    missing from the list it opened. The served classes, and no direction."""

    async def _drill(self, api_client, budget, **params):
        r = await api_client.get(
            f"/api/v1/{budget.id}/transactions",
            params={
                "scope": "leaf",
                "posted_only": True,
                "cash_flow_only": True,
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                **params,
            },
        )
        assert r.status_code == 200, r.text
        return -money(r.json()["total_amount"])

    async def test_a_category_bar(self, db_session, api_client):
        budget, cats = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "spending-grouped", start_date="2026-01-01", end_date="2026-01-31"
        )
        classes = ",".join(body["counted_classes"])
        bar = next(money(g["total"]) for g in body["groups"] if g["name"] == "Groceries")
        drilled = await self._drill(
            api_client, budget, category_ids=str(cats["groceries"].id), activity_classes=classes
        )
        assert drilled == bar == Decimal("250.00")

    async def test_the_uncategorized_line(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "spending-grouped", start_date="2026-01-01", end_date="2026-01-31"
        )
        classes = ",".join(body["counted_classes"])
        line = next(money(g["total"]) for g in body["groups"] if g["id"] is None)
        drilled = await self._drill(api_client, budget, no_category=True, activity_classes=classes)
        assert drilled == line == Decimal("40.00")

    async def test_the_expenses_bar_reads_its_classes_from_the_server(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        body = await _get(api_client, budget, "income-expense", months=3)
        assert body["expense_classes"] == ["spending"]


class TestWhereItWentRowsOpenWhatTheyCount:
    """Where it went ranks groups, categories and payees from two reports, and
    every row opens a list. Each list must total its row, with the drill
    parameters the page sends (`WhereItWentReport.openLine` and
    `openGroupTransactions`): the served classes, leaf rows, no direction.
    The group row is summed on the client from the categories in it, so its
    list is the one no server figure vouched for."""

    WHOLE = {"start_date": "2026-01-01", "end_date": TODAY.isoformat()}

    async def _drill(self, api_client, budget, **params):
        return await TestDrillsTotalWhatChartsTotal()._drill(api_client, budget, **params)

    async def test_a_group_row(self, db_session, api_client):
        budget, cats = await _household(db_session, api_client)
        body = await _get(api_client, budget, "spending-grouped", **self.WHOLE)
        classes = ",".join(body["counted_classes"])
        # 450 of groceries less its 50 refund, 120 of dining, and the 90
        # Shopping took back: the group's categories summed, as the table does.
        row = sum(
            (money(g["total"]) for g in body["groups"] if g["parent_name"] == "Everyday"),
            Decimal("0"),
        )
        members = ",".join(str(cats[k].id) for k in ("groceries", "dining", "shopping"))
        drilled = await self._drill(
            api_client, budget, category_ids=members, activity_classes=classes, **self.WHOLE
        )
        assert drilled == row == Decimal("480.00")

    async def test_a_line_that_took_back_more_than_it_spent(self, db_session, api_client):
        budget, cats = await _household(db_session, api_client)
        feb = {"start_date": "2026-02-01", "end_date": "2026-02-28"}
        body = await _get(api_client, budget, "spending-grouped", **feb)
        classes = ",".join(body["counted_classes"])
        row = next(money(g["total"]) for g in body["groups"] if g["name"] == "Shopping")
        drilled = await self._drill(
            api_client,
            budget,
            category_ids=str(cats["shopping"].id),
            activity_classes=classes,
            **feb,
        )
        assert drilled == row == Decimal("-90.00")

    async def test_a_payee_row(self, db_session, api_client):
        """Alder Street Goods: 40 uncategorized and 120 of dining, less the 90
        Shopping return — a payee whose refund sits inside its row."""
        budget, _ = await _household(db_session, api_client)
        body = await _get(api_client, budget, "payee-analysis", **self.WHOLE)
        classes = ",".join(body["counted_classes"])
        for name, expected in (("Corner Market", "450.00"), ("Alder Street Goods", "70.00")):
            payee = next(p for p in body["payees"] if p["payee_name"] == name)
            drilled = await self._drill(
                api_client,
                budget,
                payee_ids=payee["payee_id"],
                activity_classes=classes,
                **self.WHOLE,
            )
            assert drilled == money(payee["total"]) == Decimal(expected), name


class TestSpendingTrendsAveragesCompleteMonths:
    async def test_the_running_month_is_not_averaged(self, db_session, api_client):
        """January 290 and February 30 are complete; March's 200 is eighteen
        days old. The page divided 520 by three."""
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "spending-trends", start_date="2026-01-01", end_date="2026-03-18"
        )
        assert body["months_averaged"] == 2
        assert money(body["avg_monthly"]) == Decimal("160.00")
        assert body["running_month"] == "2026-03-01"

    async def test_a_range_cut_mid_month_averages_only_its_whole_months(
        self, db_session, api_client
    ):
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "spending-trends", start_date="2026-01-15", end_date="2026-02-28"
        )
        assert body["months_averaged"] == 1
        assert money(body["avg_monthly"]) == Decimal("30.00")
        # It ends before the running month, so none is drawn "so far".
        assert body["running_month"] is None

    async def test_no_complete_month_is_no_average(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "spending-trends", start_date="2026-03-01", end_date="2026-03-18"
        )
        assert body["months_averaged"] == 0
        assert body["avg_monthly"] is None


class TestDayPatternsAveragesPerCalendarDay:
    async def test_quiet_days_count_and_days_before_history_do_not(self, db_session, api_client):
        """The first transaction is 10 January (a Saturday), so a range from 1
        January counts from there: Saturdays 10, 17, 24 and 31, four of them.
        300 spent on one of them is 75 a typical Saturday — per transaction it
        read 300."""
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "day-patterns", start_date="2026-01-01", end_date="2026-01-31"
        )
        saturday = next(d for d in body["days"] if d["day_name"] == "Saturday")
        assert body["window_start"] == "2026-01-10"
        assert body["window_end"] == "2026-01-31"
        assert saturday["weekdays"] == 4
        assert money(saturday["avg_per_day"]) == Decimal("75.00")

    async def test_the_window_stops_at_today(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        body = await _get(
            api_client, budget, "day-patterns", start_date="2026-03-01", end_date="2026-03-31"
        )
        assert body["window_end"] == TODAY.isoformat()


class TestTheTimelineCanShowOutflowsOnly:
    async def test_outflows_only(self, db_session, api_client):
        budget, _ = await _household(db_session, api_client)
        every = await _get(
            api_client, budget, "large-transactions", start_date="2026-01-01", end_date="2026-03-18"
        )
        out = await _get(
            api_client,
            budget,
            "large-transactions",
            start_date="2026-01-01",
            end_date="2026-03-18",
            outflows_only="true",
        )
        assert any(money(t["amount"]) > 0 for t in every["transactions"])
        assert out["transactions"]
        assert all(money(t["amount"]) < 0 for t in out["transactions"])
