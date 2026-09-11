"""The basic reports that were missing: spending over time for a chosen set
of categories, income by source, one category's month-by-month history, and
what the essentials reserve is measured against.

Amounts are round on purpose so every figure can be checked on paper.
"""

from datetime import date
from decimal import Decimal

from igab.domain.dates import add_months
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_basics import income_by_source, spending_trends
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_payee,
    create_tag,
    create_transaction,
)

TODAY = date.today()
THIS = TODAY.replace(day=1)
LAST = add_months(THIS, -1)


async def _setup(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    fun = await create_category(db_session, budget, group, "Fun")
    await create_transaction(db_session, budget, checking, "-100.00", LAST, category=groceries)
    await create_transaction(db_session, budget, checking, "-150.00", THIS, category=groceries)
    await create_transaction(db_session, budget, checking, "-40.00", THIS, category=fun)
    await db_session.commit()
    return budget, checking, group, groceries, fun


class TestSpendingTrends:
    async def test_one_series_per_category_with_zero_filled_months(self, db_session, api_client):
        budget, _, _, groceries, fun = await _setup(db_session, api_client)
        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/spending-trends",
            params={"start_date": LAST.isoformat(), "end_date": TODAY.isoformat()},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["months"] == [LAST.isoformat(), THIS.isoformat()]
        by_name = {s["name"]: s for s in body["series"]}
        assert [Decimal(str(v)) for v in by_name["Groceries"]["monthly"]] == [
            Decimal("100.00"),
            Decimal("150.00"),
        ]
        assert [Decimal(str(v)) for v in by_name["Fun"]["monthly"]] == [
            Decimal("0"),
            Decimal("40.00"),
        ]
        assert [Decimal(str(v)) for v in body["monthly_totals"]] == [
            Decimal("100.00"),
            Decimal("190.00"),
        ]
        assert Decimal(str(body["total"])) == Decimal("290.00")
        # Largest first, so the chart's top series is the one that matters.
        assert body["series"][0]["name"] == "Groceries"
        assert body["series"][0]["group_name"] == "Everyday"

    async def test_a_saved_filter_scopes_it_and_a_tag_joins_the_scope(self, db_session, api_client):
        budget, _, _, groceries, fun = await _setup(db_session, api_client)
        r = await api_client.post(
            f"/api/v1/{budget.id}/filters",
            json={"name": "Food", "category_ids": [str(groceries.id)]},
        )
        filter_id = r.json()["id"]
        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/spending-trends",
            params={
                "start_date": LAST.isoformat(),
                "end_date": TODAY.isoformat(),
                "filter_id": filter_id,
            },
        )
        assert [s["name"] for s in r.json()["series"]] == ["Groceries"]

        tag = await create_tag(db_session, budget, "Wants")
        await db_session.commit()
        await api_client.put(
            f"/api/v1/{budget.id}/categories/{fun.id}/tags", json={"tag_ids": [str(tag.id)]}
        )
        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/spending-trends",
            params={
                "start_date": LAST.isoformat(),
                "end_date": TODAY.isoformat(),
                "filter_id": filter_id,
                "tag_ids": str(tag.id),
            },
        )
        assert sorted(s["name"] for s in r.json()["series"]) == ["Fun", "Groceries"]

    async def test_a_missing_filter_is_said_not_silently_dropped(self, db_session, api_client):
        budget, *_ = await _setup(db_session, api_client)
        import uuid

        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/spending-trends",
            params={"filter_id": str(uuid.uuid4())},
        )
        assert r.status_code == 200
        assert r.json()["filter_unavailable"] is True

    async def test_it_totals_what_the_spending_rollup_totals(self, db_session, api_client):
        """Same predicate set (`_spending_query`): the trends' grand total
        equals the grouped report's total over the same window."""
        budget, *_ = await _setup(db_session, api_client)
        params = {"start_date": LAST.isoformat(), "end_date": TODAY.isoformat()}
        trends = (
            await api_client.get(f"/api/v1/{budget.id}/reports/spending-trends", params=params)
        ).json()
        grouped = (
            await api_client.get(f"/api/v1/{budget.id}/reports/spending-grouped", params=params)
        ).json()
        assert Decimal(str(trends["total"])) == Decimal(str(grouped["total"]))


class TestIncomeBySource:
    async def test_income_per_payee_per_month(self, db_session, api_client):
        budget, checking, _, groceries, _ = await _setup(db_session, api_client)
        payserv = await create_payee(db_session, budget, "Northwind Payserv")
        side = await create_payee(db_session, budget, "Side Gig")
        await create_transaction(db_session, budget, checking, "3000.00", LAST, payee=payserv)
        await create_transaction(db_session, budget, checking, "3000.00", THIS, payee=payserv)
        await create_transaction(db_session, budget, checking, "250.00", THIS, payee=side)
        # A refund into an envelope is not income.
        await create_transaction(
            db_session, budget, checking, "20.00", THIS, payee=side, category=groceries
        )
        await db_session.commit()

        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/income-by-source", params={"months": 2}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["months"] == [LAST.isoformat(), THIS.isoformat()]
        by_name = {s["payee_name"]: s for s in body["sources"]}
        assert [Decimal(str(v)) for v in by_name["Northwind Payserv"]["monthly"]] == [
            Decimal("3000.00"),
            Decimal("3000.00"),
        ]
        assert [Decimal(str(v)) for v in by_name["Side Gig"]["monthly"]] == [
            Decimal("0"),
            Decimal("250.00"),
        ]
        assert Decimal(str(body["total"])) == Decimal("6250.00")
        assert body["sources"][0]["payee_name"] == "Northwind Payserv"


class TestCategoryHistory:
    async def test_month_by_month_figures_are_the_budget_pages(self, db_session, api_client):
        budget, _, _, groceries, _ = await _setup(db_session, api_client)
        await create_budget_assignment(db_session, budget, groceries, THIS, "200.00")
        await db_session.commit()
        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/category-history",
            params={"category_id": str(groceries.id), "months": 2},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["category_name"] == "Groceries"
        assert [m["month"] for m in body["months"]] == [LAST.isoformat(), THIS.isoformat()]
        this = body["months"][1]
        assert Decimal(str(this["activity"])) == Decimal("-150.00")
        # Whatever the assignment call did, the served figure is the budget
        # page's own: assigned + carried − spent.
        month = (await api_client.get(f"/api/v1/{budget.id}/months/{THIS.isoformat()}")).json()
        row = next(b for b in month["category_balances"] if b["category_id"] == str(groceries.id))
        assert Decimal(str(this["available"])) == Decimal(str(row["available"]))
        assert Decimal(str(this["assigned"])) == Decimal(str(row["assigned"]))

    async def test_an_income_category_publishes_no_available(self, db_session, api_client):
        """ "Income categories do not hold money" — the app's own rule, raised by
        `BudgetService._require_envelope`, and the budget page draws no balance
        for one. This report served it anyway, under a docstring promising the
        budget page's own numbers: a paycheque category read a lifetime
        carryover of every dollar ever earned, in a column headed Available.

        The month-by-month ACTIVITY is meaningful and stays.
        """
        budget, checking, *_ = await _setup(db_session, api_client)
        income = await create_category_group(db_session, budget, "Income", is_system=True)
        salary = await create_category(db_session, budget, income, "Salary")
        await create_transaction(db_session, budget, checking, "2500.00", LAST, category=salary)
        await create_transaction(db_session, budget, checking, "2500.00", THIS, category=salary)
        await db_session.commit()

        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/category-history",
            params={"category_id": str(salary.id), "months": 2},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert [m["available"] for m in body["months"]] == [None, None]
        assert Decimal(str(body["months"][1]["activity"])) == Decimal("2500.00")

    async def test_a_spending_categorys_available_is_still_served(self, db_session, api_client):
        """The other side of the same fork: None is for the categories that
        hold no money, never a blanket "we stopped answering"."""
        budget, _, _, groceries, _ = await _setup(db_session, api_client)
        await create_budget_assignment(db_session, budget, groceries, THIS, "200.00")
        await db_session.commit()
        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/category-history",
            params={"category_id": str(groceries.id), "months": 1},
        )
        assert Decimal(str(r.json()["months"][0]["available"])) == Decimal("50.00")

    async def test_another_budgets_category_is_not_found(self, db_session, api_client):
        budget, *_ = await _setup(db_session, api_client)
        other = await create_budget(db_session, api_client.test_user, name="Other")
        group = await create_category_group(db_session, other, "G")
        foreign = await create_category(db_session, other, group, "Theirs")
        await db_session.commit()
        r = await api_client.get(
            f"/api/v1/{budget.id}/reports/category-history",
            params={"category_id": str(foreign.id)},
        )
        assert r.status_code == 404


class TestEssentialsRunway:
    async def test_runway_is_the_fund_over_a_lean_month(self, db_session, api_client):
        budget, checking, group, groceries, _ = await _setup(db_session, api_client)
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        essential = await tags.get_system_tag(budget.id, "essential")
        savings = await tags.get_system_tag(budget.id, "savings")
        await tags.set_category_tags(groceries.id, [essential.id])
        emergency = await create_category(db_session, budget, group, "Emergency Fund")
        await tags.set_category_tags(emergency.id, [savings.id])
        await db_session.commit()
        # 500 into the fund: assigned this month, nothing spent.
        await create_budget_assignment(db_session, budget, emergency, THIS, "500.00")
        await db_session.commit()

        r = await api_client.get(f"/api/v1/{budget.id}/reports/essentials")
        assert r.status_code == 200, r.text
        body = r.json()
        # 250 of essential spend in the last 90 days ÷ 3 = 83.33 a month.
        headline = Decimal(str(body["essentials_90d"]))
        assert headline == Decimal("83.33")
        assert Decimal(str(body["emergency_fund_balance"])) == Decimal("500.00")
        assert body["emergency_fund_source"]
        assert Decimal(str(body["runway_months"])) == (Decimal("500") / headline).quantize(
            Decimal("0.1")
        )

    async def test_no_fund_means_no_runway_not_zero(self, db_session, api_client):
        budget, *_ = await _setup(db_session, api_client)
        r = await api_client.get(f"/api/v1/{budget.id}/reports/essentials")
        body = r.json()
        assert body["emergency_fund_balance"] is None
        assert body["runway_months"] is None


async def test_cost_of_living_rolls_essentials_up_by_group(db_session, api_client):
    """Built on the Essential tag rather than a sixth system tag: the groups a
    budget already has are the shape a household thinks in."""
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    tag_repo = TagRepository(db_session)
    await seed_system_tags(db_session, budget.id)
    essential = await tag_repo.get_system_tag(budget.id, "essential")

    housing = await create_category_group(db_session, budget, "Housing")
    rent = await create_category(db_session, budget, housing, "Rent")
    utilities = await create_category_group(db_session, budget, "Utilities")
    power = await create_category(db_session, budget, utilities, "Power")
    fun = await create_category_group(db_session, budget, "Fun")
    dining = await create_category(db_session, budget, fun, "Dining")
    for cat in (rent, power):
        await tag_repo.set_category_tags(cat.id, [essential.id])

    today = date.today()

    async def spend(amount: str, category):
        await create_transaction(
            db_session, budget, checking, Decimal(amount), today, category=category
        )

    await spend("-1400.00", rent)
    await spend("-180.00", power)
    # Untagged: not a cost of living, however regular.
    await spend("-90.00", dining)
    await db_session.commit()

    r = await api_client.get(f"/api/v1/{budget.id}/reports/cost-of-living", params={"months": 3})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["tagged"] is True
    assert body["basis"] == "tag"
    groups = {g["group_name"]: g for g in body["groups"]}
    assert set(groups) == {"Housing", "Utilities"}
    assert Decimal(groups["Housing"]["total"]) == Decimal("1400.00")
    assert Decimal(groups["Utilities"]["total"]) == Decimal("180.00")
    # Shares are of the essentials total, so they add to 100.
    assert sum(Decimal(g["share"]) for g in body["groups"]) == Decimal("100.00")
    # Biggest first.
    assert [g["group_name"] for g in body["groups"]] == ["Housing", "Utilities"]


async def test_cost_of_living_says_when_nothing_is_tagged(db_session, api_client):
    """With no Essential tag applied the scope is every category, which equals
    plain burn rate — the page has to say so rather than present it as a
    chosen few."""
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()

    r = await api_client.get(f"/api/v1/{budget.id}/reports/cost-of-living")

    assert r.status_code == 200, r.text
    assert r.json()["tagged"] is False
    assert r.json()["basis"] == "all"
    # No income on record: a ratio against zero is unknown, not 100%.
    assert r.json()["required_ratio"] is None


class TestTheClassRuleIsOneRule:
    """Three spending rollups widen their class set for an explicit account
    selection, and the third copy of that rule did not have it.

    `counted_classes` is now the one home. Pointing the account filter at a
    tracked account used to draw nothing on Spending Trends beside a populated
    Spending Breakdown over the identical selection — and the note that
    explains an exclusion was suppressed too, because nothing had been
    excluded: the rows were simply never counted.
    """

    async def test_a_tracked_account_selection_totals_the_same_on_both(
        self, db_session, api_client
    ):
        budget, checking, group, groceries, fun = await _setup(db_session, api_client)
        brokerage = await create_account(
            db_session,
            budget,
            "Cascade Point Brokerage",
            account_type="investment",
            on_budget=False,
        )
        fees = await create_category(db_session, budget, group, "Brokerage Fees")
        # An outflow on a tracking account classifies investment_return, never
        # spending — which is why an explicit selection has to widen.
        await create_transaction(db_session, budget, brokerage, "-180.00", THIS, category=fees)
        await db_session.commit()

        svc = ReportService(db_session)
        window = (add_months(THIS, -1), TODAY)
        trends = await spending_trends(svc, budget.id, *window, account_ids=[brokerage.id])
        _items, grouped_total, _meta = await svc.spending_grouped(
            budget.id, *window, account_ids=[brokerage.id]
        )

        assert trends["total"] == Decimal("180.00")
        assert trends["total"] == grouped_total

    async def test_an_empty_account_scope_returns_nothing_not_everything(
        self, db_session, api_client
    ):
        """`None` means no scope was asked for; `[]` means one was asked for
        and nothing matched. `if account_ids:` conflated them, so scoping to a
        tag nobody has applied answered with the whole budget.
        """
        budget, checking, group, groceries, fun = await _setup(db_session, api_client)
        svc = ReportService(db_session)
        window = (add_months(THIS, -1), TODAY)

        _u, unscoped_total, _um = await svc.spending_grouped(budget.id, *window)
        _e, empty_total, _em = await svc.spending_grouped(budget.id, *window, account_ids=[])

        assert unscoped_total == Decimal("290.00")
        assert empty_total == Decimal("0")


class TestIncomeIsDecidedByClassNotSign:
    async def test_a_clawed_back_paycheque_reduces_its_payees_income(self, db_session, api_client):
        """The classifier's income rule is "(amount > 0 AND uncategorized) OR
        the category is in a system group", so a NEGATIVE row filed to an
        inflow category is negative income. `Transaction.amount > 0` in the
        WHERE dropped it, and this report's total then exceeded the income
        Income vs Expenses serves for the same window.
        """
        budget, checking, group, groceries, fun = await _setup(db_session, api_client)
        system = await create_category_group(db_session, budget, "Income", is_system=True)
        inflow = await create_category(db_session, budget, system, "Ready to Assign")
        payserv = await create_payee(db_session, budget, "Northwind Payserv")

        await create_transaction(
            db_session, budget, checking, "3000.00", THIS, payee=payserv, category=inflow
        )
        await create_transaction(
            db_session, budget, checking, "-400.00", THIS, payee=payserv, category=inflow
        )
        await db_session.commit()

        svc = ReportService(db_session)
        by_source = await income_by_source(db_session, budget.id, months=2)
        headline = await svc.income_vs_expense(budget.id, months=2)

        # 2600, not 3000 — and the same figure the cash-flow report gives.
        assert by_source["total"] == Decimal("2600.00")
        assert sum(m["income"] for m in headline) == by_source["total"]
        assert by_source["sources"][0]["total"] == Decimal("2600.00")
