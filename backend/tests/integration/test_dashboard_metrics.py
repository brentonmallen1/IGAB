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

from igab.repositories.asset_repo import AssetRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_service import ReportService
from igab.services.transaction_service import TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_liability,
    create_liability_snapshot,
    create_transaction,
    create_transfer,
    create_user,
    make_services,
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
        # None, not 0.0. The live path and the schema both say None when there
        # is no income, and this path is the one a brand-new budget takes — so
        # 0.0 told every new household it had saved none of its income.
        assert card["savings_rate"] is None

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

    async def test_savings_rate_is_unknown_without_income(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        group = await create_category_group(db_session, budget, "Everyday")
        cat = await create_category(db_session, budget, group, "Groceries")
        await create_transaction(db_session, budget, checking, "-50.00", TODAY, category=cat)
        await db_session.flush()

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        # None, not 0.0. "No income recorded" and "saved nothing" are different
        # facts, and this card sat beside a Savings Rate tab that already said
        # so — the two carried one label and disagreed on exactly the months a
        # new budget starts with.
        assert card["savings_rate"] is None

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


class TestTopSpendingIsSpending:
    """`top_categories` partitioned on `amount < 0` alone, two screens below a
    comment claiming every figure on the card uses the activity-class
    partition. So a transfer to a brokerage and a mortgage principal payment
    were listed as the household's biggest spending.
    """

    async def test_a_savings_transfer_is_not_top_spending(self, db_session):
        budget = await create_budget(db_session, await create_user(db_session))
        checking = await create_account(db_session, budget, "Checking")
        brokerage = await create_account(
            db_session, budget, "Cascade Point HYSA", account_type="investment", on_budget=False
        )
        group = await create_category_group(db_session, budget, "Everyday")
        savings = await create_category(db_session, budget, group, "Investing")
        groceries = await create_category(db_session, budget, group, "Groceries")

        # The transfer is far larger, so before the fix it took the top slot.
        await create_transfer(
            db_session, budget, checking, brokerage, "2000.00", TODAY, category=savings
        )
        await create_transaction(db_session, budget, checking, "-310.00", TODAY, category=groceries)
        await db_session.commit()

        data = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        assert [c["name"] for c in data["top_categories"]] == ["Groceries"]

    async def test_the_card_shows_three_when_three_exist(self, db_session):
        """The top 3 were taken BEFORE the category lookup, and the lookup used
        BUDGETED_ENVELOPE — which drops a deleted category. A category deleted
        after the money left it did not unspend the money, so the row belongs
        in the ranking; under the old order the card silently drew two.
        """
        budget = await create_budget(db_session, await create_user(db_session))
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Everyday")
        names = ["Rent", "Groceries", "Fun", "Transport"]
        amounts = ["-1400.00", "-600.00", "-200.00", "-90.00"]
        cats = []
        for name, amount in zip(names, amounts, strict=True):
            cat = await create_category(db_session, budget, group, name)
            await create_transaction(db_session, budget, checking, amount, TODAY, category=cat)
            cats.append(cat)
        # Delete the biggest one: it stays in the ranking, and the card still
        # fills three slots rather than two.
        cats[0].is_deleted = True
        await db_session.commit()

        data = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        assert len(data["top_categories"]) == 3
        assert [c["name"] for c in data["top_categories"]] == ["Rent", "Groceries", "Fun"]


class TestABudgetWithNoTransactionsStillOwnsThings:
    async def test_an_unmanaged_liability_is_net_worth_even_with_no_rows(self, db_session):
        """The empty short-circuit returned a flat zero, so a household that
        had entered its mortgage as an unmanaged liability read net worth 0 —
        and `net_worth_history`, which counts it, disagreed with the card on a
        surface where the two are asserted to agree.
        """
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        # `manual_balance` is what the "now" figure reads; the snapshot feeds
        # the historical series behind the chart's earlier points.
        loan = await create_liability(
            db_session,
            budget,
            "Harborstone Mortgage",
            liability_type="mortgage",
            manual_balance=Decimal("240000.00"),
        )
        await create_liability_snapshot(db_session, loan, TODAY, Decimal("240000.00"))

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)
        chart = await ReportService(db_session).net_worth_history(budget.id, months=1)

        assert card["net_worth"] == Decimal("-240000.00")
        assert Decimal(str(chart[-1]["net_worth"])) == card["net_worth"]

    async def test_a_stated_house_and_its_mortgage(self, db_session):
        """The asset half of the same fix had no test: every asset test builds
        its budget by posting a row, so none reached the empty path. Dropping
        the house — the direction that reads a household as underwater —
        passed.
        """
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        house = await AssetRepository(db_session).create(budget_id=budget.id, name="Maple St House")
        await AssetRepository(db_session).upsert_value(house, TODAY, Decimal("300000.00"))
        loan = await create_liability(
            db_session, budget, "Harborstone Mortgage", manual_balance=Decimal("240000.00")
        )
        await create_liability_snapshot(db_session, loan, TODAY, Decimal("240000.00"))

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)
        chart = await ReportService(db_session).net_worth_history(budget.id, months=1)

        assert card["net_worth"] == Decimal("60000.00")
        assert chart[-1]["net_worth"] == Decimal("60000.00")

    async def test_the_change_is_read_as_it_stood_before_the_window(self, db_session):
        """The empty path set `net_worth_prev` to "now", so the card drew a
        0.0% change beside a chart stepping from one figure to another, and a
        house re-appraised during the window read unchanged. One $0.01 row
        sent the same budget down the live path and a different answer.

        The house stood at 280,000 before the window and 300,000 now; the
        mortgage was first recorded today, so it is in "now" and not before.
        """
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        house = await AssetRepository(db_session).create(budget_id=budget.id, name="Maple St House")
        before = MONTH_START - timedelta(days=10)
        await AssetRepository(db_session).upsert_value(house, before, Decimal("280000.00"))
        await AssetRepository(db_session).upsert_value(house, TODAY, Decimal("300000.00"))
        loan = await create_liability(
            db_session, budget, "Harborstone Mortgage", manual_balance=Decimal("240000.00")
        )
        await create_liability_snapshot(db_session, loan, TODAY, Decimal("240000.00"))

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)
        chart = await ReportService(db_session).net_worth_history(budget.id, months=2)

        assert card["net_worth"] == Decimal("60000.00")
        assert card["net_worth_prev"] == Decimal("280000.00")
        # The window opens on the 1st, so "before it" is last month's point.
        assert chart[-2]["net_worth"] == Decimal("280000.00")

    async def test_tagged_essentials_are_zero_not_untagged(self, db_session):
        """The empty path hard-coded "nothing tagged", so a new budget with
        Rent tagged Essential was asked to tag something Essential — until
        its first transaction, when the card read $0.00."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        group = await create_category_group(db_session, budget, "Bills")
        rent = await create_category(db_session, budget, group, "Rent")
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        essential = next(
            t for t in await tags.list_for_budget(budget.id) if t.system_key == "essential"
        )
        await tags.set_category_tags(rent.id, [essential.id])

        card = await ReportService(db_session).dashboard_metrics(budget.id, MONTH_START, TODAY)

        assert card["essentials_tagged"] is True
        assert card["essentials_monthly"] == Decimal("0")


class TestNetWorthAtTheWindowStart:
    async def test_prev_counts_rows_before_the_window_and_the_debt_as_it_stood(self, db_session):
        """`net_worth_prev` — the Overview's net-worth change — became one SQL
        aggregate with nothing pinning its bound. A slip to `<= start_date`
        counts the first day of the window as the past; a slip to `<= today`
        makes the change zero. Every row below sits on one side of a bound,
        and the unmanaged debt is read as it stood the day before the window.
        """
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        gas = await create_category(db_session, budget, group, "Gas")
        start = TODAY - timedelta(days=10)

        await create_transaction(db_session, budget, checking, "1000.00", start - timedelta(days=5))
        await create_transaction(db_session, budget, checking, "200.00", start)
        await create_transaction(db_session, budget, checking, "50.00", TODAY)
        # Not money that has moved yet: in neither figure.
        await create_transaction(db_session, budget, checking, "7.00", TODAY + timedelta(days=5))
        # A split before the window: counted once, by its parent.
        when = start - timedelta(days=3)
        await make_services(db_session).transactions.create_split(
            budget.id,
            TransactionCreate(account_id=checking.id, date=when, amount=Decimal("-100.00")),
            [
                TransactionCreate(
                    account_id=checking.id,
                    date=when,
                    amount=Decimal("-60.00"),
                    category_id=groceries.id,
                ),
                TransactionCreate(
                    account_id=checking.id, date=when, amount=Decimal("-40.00"), category_id=gas.id
                ),
            ],
        )
        # An unmanaged debt that stood at 800 before the window and 500 now.
        loan = await create_liability(
            db_session, budget, "Harborstone Loan", manual_balance=Decimal("500.00")
        )
        await create_liability_snapshot(
            db_session, loan, start - timedelta(days=6), Decimal("800.00")
        )
        await create_liability_snapshot(db_session, loan, TODAY, Decimal("500.00"))

        card = await ReportService(db_session).dashboard_metrics(budget.id, start, TODAY)

        # Now: 1000 + 200 + 50 − 100 = 1150, less the 500 owed.
        assert card["net_worth"] == Decimal("650.00")
        # Before the window: 1000 − 100 = 900, less the 800 owed then.
        assert card["net_worth_prev"] == Decimal("100.00")
