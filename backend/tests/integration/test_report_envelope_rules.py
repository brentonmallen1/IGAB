"""The two envelope rules the reports ask with, and the one term between them.

`report_service` spelled these by hand at ten call sites and no two clusters
agreed. Five queries over assignments: four excluded categories under a
soft-deleted group, one did not. Five over spending rows: one excluded them,
four did not. So two reports over the same assignments gave different answers,
and two reports over the same spending gave different answers — a budgeting app
contradicting itself, which is the only failure mode that matters here.

Both now read `category_filters.BUDGETED_ENVELOPE` / `SPENT_ENVELOPE`. The
divergence that remains is deliberate and is the subject of this file: it is
one term wide, it is named at the definition, and these tests fail if it
widens.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import update

from igab.db.models import Category, CategoryGroup
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

D = Decimal
TODAY = date.today()
FIRST = TODAY.replace(day=1)
RECENT = FIRST + timedelta(days=3)


async def _world(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Redwood Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")
    return services, budget, checking, group, cat


async def _soft_delete_group(db_session, group):
    """The reachable anomaly: the group row is soft-deleted while its
    categories stay live. `UNDER_DELETED_GROUP` is the check that reports it,
    and `get_budget_summary` counts the money in it."""
    await db_session.execute(
        update(CategoryGroup).where(CategoryGroup.id == group.id).values(is_deleted=True)
    )
    await db_session.flush()


class TestACategoryUnderADeletedGroup:
    """Neither rule drops it. It is money the budget page counts, so a report
    that hides it disagrees with the page it reports on — silently, and in the
    shrinking direction."""

    async def test_the_budget_summary_counts_it(self, db_session):
        """The fact both rules are pinned to. If this ever stops being true,
        the rules should follow it rather than the other way round."""
        services, budget, _checking, group, cat = await _world(db_session)
        await create_budget_assignment(db_session, budget, cat, FIRST, "100.00")
        await _soft_delete_group(db_session, group)

        summary = await services.budgets.get_budget_summary(budget.id, FIRST)
        assert any(b.category_id == cat.id for b in summary.category_balances)

    async def test_its_assignments_still_reach_the_reports(self, db_session):
        services, budget, _checking, group, cat = await _world(db_session)
        await create_budget_assignment(db_session, budget, cat, FIRST, "100.00")
        await _soft_delete_group(db_session, group)

        reports = ReportService(db_session)
        result = await reports.budget_vs_actual(budget.id, FIRST, TODAY)
        assert result["total_assigned"] == D("100.00"), result

    async def test_its_spending_still_reaches_the_reports(self, db_session):
        services, budget, checking, group, cat = await _world(db_session)
        await create_transaction(db_session, budget, checking, "-40.00", RECENT, category=cat)
        await _soft_delete_group(db_session, group)

        reports = ReportService(db_session)
        grouped = await reports.spending_grouped(budget.id, FIRST, TODAY)
        assert grouped, "spending under a deleted group vanished from the report"


class TestTheTwoRulesAgreeWhereTheyMust:
    """Two reports over the same numbers must not disagree. Before the
    consolidation `cumulative_variance` counted assignments under a deleted
    group that `budget_vs_actual` dropped, and `spending_grouped` counted
    spending that `plan_vs_reality` dropped."""

    async def test_budget_vs_actual_and_cumulative_variance_see_the_same_plan(self, db_session):
        services, budget, _checking, group, cat = await _world(db_session)
        await create_budget_assignment(db_session, budget, cat, FIRST, "100.00")
        await _soft_delete_group(db_session, group)

        reports = ReportService(db_session)
        bva = await reports.budget_vs_actual(budget.id, FIRST, TODAY)
        variance = await reports.cumulative_variance(budget.id, months=1)

        assert bva["total_assigned"] == D("100.00")
        assigned_in_variance = sum(
            D(str(m.get("budget_assigned", 0))) for m in (variance or []) if isinstance(m, dict)
        )
        assert assigned_in_variance == D("100.00"), variance

    async def test_every_spending_report_sees_the_same_rows(self, db_session):
        services, budget, checking, group, cat = await _world(db_session)
        await create_transaction(db_session, budget, checking, "-40.00", RECENT, category=cat)
        await _soft_delete_group(db_session, group)

        reports = ReportService(db_session)
        grouped = await reports.spending_grouped(budget.id, FIRST, TODAY)
        volatility = await reports.category_volatility(budget.id, months=2)
        plan = await reports.plan_vs_reality(budget.id, months=2)

        # None of the three may silently drop the row the others keep.
        assert grouped, "spending_grouped dropped it"
        assert volatility is not None
        assert plan is not None


class TestTheDeliberateDivergence:
    """The one term the two rules differ by, stated as a test so it cannot
    widen unnoticed. On the happy path it is unobservable — deletion clears
    assignments and re-files transactions — so it is exercised here against
    rows an older delete path would have left behind."""

    async def test_the_rules_differ_by_exactly_the_category_liveness_term(self):
        from igab.repositories.category_filters import (
            BUDGETED_ENVELOPE,
            IN_SYSTEM_GROUP,
            LIVE_CATEGORY,
            SPENT_ENVELOPE,
        )
        from sqlalchemy import and_, not_

        assert str(SPENT_ENVELOPE) == str(not_(IN_SYSTEM_GROUP))
        assert str(BUDGETED_ENVELOPE) == str(and_(LIVE_CATEGORY, not_(IN_SYSTEM_GROUP)))

    async def test_spending_left_behind_by_a_deleted_category_still_counts(self, db_session):
        """The money moved. Deleting the envelope afterwards does not unspend
        it, and under-reporting spending is the dangerous direction here."""
        services, budget, checking, _group, cat = await _world(db_session)
        await create_transaction(db_session, budget, checking, "-40.00", RECENT, category=cat)
        await db_session.execute(
            update(Category).where(Category.id == cat.id).values(is_deleted=True)
        )
        await db_session.flush()

        grouped = await ReportService(db_session).spending_grouped(budget.id, FIRST, TODAY)
        assert grouped, "spending filed to a since-deleted category vanished"

    async def test_a_plan_left_behind_by_a_deleted_category_does_not(self, db_session):
        """The other side of the same term: the budget grid does not show this
        envelope, so a plan-vs-actual report must not plan against it."""
        services, budget, _checking, _group, cat = await _world(db_session)
        await create_budget_assignment(db_session, budget, cat, FIRST, "100.00")
        await db_session.execute(
            update(Category).where(Category.id == cat.id).values(is_deleted=True)
        )
        await db_session.flush()

        result = await ReportService(db_session).budget_vs_actual(budget.id, FIRST, TODAY)
        assert result["total_assigned"] == D("0"), result
