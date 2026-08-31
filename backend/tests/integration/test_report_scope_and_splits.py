"""Two ways a report showed the wrong rows once class filtering arrived.

Both are interactions, not isolated defects: the class filter is correct, the
account scope is correct, and the split handling is correct — but composed in
the wrong order they cancel each other out. That is why unit coverage of each
piece passed while the composition was broken.
"""

from datetime import date
from decimal import Decimal

from igab.repositories.tag_repo import TagRepository
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_tag,
    create_transaction,
    create_user,
)

TODAY = date.today()
MONTH_START = TODAY.replace(day=1)


class TestExplicitAccountScopeBeatsTheClassFilter:
    """Picking a tracked account in the report filter returned an empty chart:
    its outflows classify investment_return / debt_interest, and the class
    filter was ANDed in before the scope override that the selection is."""

    async def _world(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )
        group = await create_category_group(db_session, budget, "Everyday")
        fees = await create_category(db_session, budget, group, "Fees")
        await create_transaction(db_session, budget, brokerage, "-50.00", TODAY, category=fees)
        await create_transaction(db_session, budget, loan, "-30.00", TODAY, category=fees)
        await create_transaction(db_session, budget, checking, "-90.00", TODAY, category=fees)
        await db_session.flush()
        return budget, checking, brokerage, loan

    async def test_spending_by_category_shows_brokerage_fees(self, db_session):
        budget, _, brokerage, _ = await self._world(db_session)
        _, total = await ReportService(db_session).spending_by_category(
            budget.id, MONTH_START, TODAY, None, [brokerage.id]
        )
        assert total == Decimal("50.00")

    async def test_spending_grouped_shows_loan_interest(self, db_session):
        budget, _, _, loan = await self._world(db_session)
        _, total, _ = await ReportService(db_session).spending_grouped(
            budget.id, MONTH_START, TODAY, None, [loan.id]
        )
        assert total == Decimal("30.00")

    async def test_day_patterns_shows_tracked_activity(self, db_session):
        budget, _, brokerage, _ = await self._world(db_session)
        result = await ReportService(db_session).day_patterns(
            budget.id, MONTH_START, TODAY, None, [brokerage.id]
        )
        assert sum(d["total"] for d in result["days"]) == Decimal("50.00")

    async def test_the_default_scope_still_excludes_them(self, db_session):
        """The widening must apply only to an explicit selection — the
        unfiltered report still means on-budget spending."""
        budget, *_ = await self._world(db_session)
        _, total = await ReportService(db_session).spending_by_category(
            budget.id, MONTH_START, TODAY
        )
        assert total == Decimal("90.00")

    async def test_selecting_an_on_budget_account_is_unaffected(self, db_session):
        budget, checking, _, _ = await self._world(db_session)
        _, total = await ReportService(db_session).spending_by_category(
            budget.id, MONTH_START, TODAY, None, [checking.id]
        )
        assert total == Decimal("90.00")


class TestSplitLegsClassifyIndividually:
    """A split parent carries no category, so it classified as plain spending
    and dragged its savings-tagged leg in with it. Leaf-based reports excluded
    the same leg, so the two disagreed about one transaction."""

    async def _split_world(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        fund = await create_category(db_session, budget, group, "Car Replacement")

        repo = TagRepository(db_session)
        tags = {t.system_key: t for t in await repo.list_for_budget(budget.id)}
        tag = tags.get("savings") or await create_tag(
            db_session, budget, "savings", system_key="savings"
        )
        await repo.set_category_tags(fund.id, [tag.id])

        shop = await create_payee(db_session, budget, "Big Box")
        parent = await create_transaction(
            db_session, budget, checking, "-300.00", TODAY, payee=shop, is_split=True
        )
        await create_transaction(
            db_session,
            budget,
            checking,
            "-100.00",
            TODAY,
            category=groceries,
            parent_transaction_id=parent.id,
        )
        await create_transaction(
            db_session,
            budget,
            checking,
            "-200.00",
            TODAY,
            category=fund,
            parent_transaction_id=parent.id,
        )
        await db_session.flush()
        return budget

    async def test_burn_rate_counts_only_the_spending_leg(self, db_session):
        budget = await self._split_world(db_session)
        points = await ReportService(db_session).burn_rate(budget.id, months=1)
        assert points[-1]["rolling_30"] == Decimal("100.00")

    async def test_burn_rate_agrees_with_the_leaf_reports(self, db_session):
        budget = await self._split_world(db_session)
        svc = ReportService(db_session)
        _, leaf_total = await svc.spending_by_category(budget.id, MONTH_START, TODAY)
        points = await svc.burn_rate(budget.id, months=1)
        assert points[-1]["rolling_30"] == leaf_total, (
            "parent-row and leaf reports must not disagree about one transaction"
        )

    async def test_payee_analysis_counts_only_the_spending_leg(self, db_session):
        budget = await self._split_world(db_session)
        payees, total = await ReportService(db_session).payee_analysis(
            budget.id, MONTH_START, TODAY
        )
        assert total == Decimal("100.00")
        assert [p["payee_name"] for p in payees] == ["Big Box"], (
            "the split's legs still attribute to the parent's payee"
        )

    async def test_an_ordinary_split_is_unchanged(self, db_session):
        """Nothing tagged: the whole basket is still spending, under one payee."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Checking", on_budget=True)
        group = await create_category_group(db_session, budget, "Everyday")
        a = await create_category(db_session, budget, group, "Groceries")
        b = await create_category(db_session, budget, group, "Household")
        shop = await create_payee(db_session, budget, "Big Box")
        parent = await create_transaction(
            db_session, budget, checking, "-75.00", TODAY, payee=shop, is_split=True
        )
        for cat, amt in ((a, "-50.00"), (b, "-25.00")):
            await create_transaction(
                db_session,
                budget,
                checking,
                amt,
                TODAY,
                category=cat,
                parent_transaction_id=parent.id,
            )
        await db_session.flush()

        payees, total = await ReportService(db_session).payee_analysis(
            budget.id, MONTH_START, TODAY
        )
        assert total == Decimal("75.00")
        assert len(payees) == 1
        assert payees[0]["count"] == 2, "legs are counted, the basket is one payee"
