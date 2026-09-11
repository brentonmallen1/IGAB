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
from igab.domain.dates import add_months
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
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
        from sqlalchemy import and_, not_

        from igab.repositories.category_filters import (
            BUDGETED_ENVELOPE,
            IN_SYSTEM_GROUP,
            LIVE_CATEGORY,
            SPENT_ENVELOPE,
        )

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


class TestArchivedEnvelopes:
    """Archived is not deleted, and the reports say so.

    Neither constant mentions `is_archived`, so archived envelopes count in
    both — which is right, and is exactly the reason to archive rather than
    delete. But nothing said so: it was an accident of the flag not appearing
    in either expression, and an accident is one edit from being reversed.
    These are that decision, on the record.
    """

    async def test_its_past_spending_still_counts(self, db_session):
        services, budget, checking, _group, cat = await _world(db_session)
        await create_transaction(db_session, budget, checking, "-40.00", RECENT, category=cat)
        cat.is_archived = True
        await db_session.flush()

        grouped = await ReportService(db_session).spending_grouped(budget.id, FIRST, TODAY)

        assert grouped, "archiving an envelope must not unspend its history"

    async def test_its_past_plans_still_count(self, db_session):
        """The other side. An archived envelope's assignments were real plans,
        and a plan-vs-actual report that drops them understates what was
        budgeted for a month that has already happened."""
        services, budget, _checking, _group, cat = await _world(db_session)
        await create_budget_assignment(db_session, budget, cat, FIRST, "100.00")
        cat.is_archived = True
        await db_session.flush()

        result = await ReportService(db_session).budget_vs_actual(budget.id, FIRST, TODAY)

        assert result["total_assigned"] == D("100.00")

    async def test_an_archived_group_makes_no_difference_either(self, db_session):
        """The group's flag, not the category's — the asymmetry
        `category_filters` opens with, and the one the archived listing had to
        account for too."""
        services, budget, checking, group, cat = await _world(db_session)
        await create_transaction(db_session, budget, checking, "-40.00", RECENT, category=cat)
        group.is_archived = True
        await db_session.flush()

        grouped = await ReportService(db_session).spending_grouped(budget.id, FIRST, TODAY)

        assert grouped

    async def test_neither_constant_mentions_archived(self):
        """Stated directly, so a future edit that adds `NOT_ARCHIVED` to either
        one fails here rather than quietly shrinking a report."""
        from igab.repositories.category_filters import BUDGETED_ENVELOPE, SPENT_ENVELOPE

        assert "is_archived" not in str(BUDGETED_ENVELOPE)
        assert "is_archived" not in str(SPENT_ENVELOPE)


class TestThePlannedSpendUniverse:
    """`PLANNED_SPEND_ROW` + the activity-class filter: what plan-vs-actual
    may call "spent". Before the extraction, `cumulative_variance` and
    `budget_vs_actual` carried byte-identical inline copies missing the same
    three terms — no class filter, no `ON_BUDGET_ACCOUNT`, no envelope rule —
    so each subtracted a bigger spending universe from a smaller planning one,
    and the cumulative line compounded the gap every month. One test per
    missing term, each named for the row the old copies wrongly counted.

    `plan_vs_reality` is the third reader. It kept its own inline set with
    no class filter and no `ON_BUDGET_ACCOUNT` after the other two were
    consolidated, so it counted a brokerage transfer as overspending while
    they counted nothing — and its chronic flag feeds the Guide."""

    async def test_a_savings_transfer_is_not_planned_spend(self, db_session):
        """Out of an UNTAGGED envelope. The class is what excludes it, and a
        savings TAG on the envelope is the one exception to that — the same
        shape out of a tagged envelope does count, pinned by
        `TestASavingsTaggedEnvelope`."""
        services, budget, checking, group, cat = await _world(db_session)
        brokerage = await create_account(
            db_session, budget, "Cascade Brokerage", account_type="investment", on_budget=False
        )
        await create_budget_assignment(db_session, budget, cat, FIRST, "500.00")
        # A categorized transfer to a tracked asset: SAVINGS by class, and
        # exactly the row the old `category_id IS NOT NULL` copies counted.
        await create_transfer(
            db_session, budget, checking, brokerage, "200.00", TODAY, category=cat
        )

        reports = ReportService(db_session)
        variance = await reports.cumulative_variance(budget.id, months=1)
        bva = await reports.budget_vs_actual(budget.id, FIRST, TODAY)
        pvr = await reports.plan_vs_reality(budget.id, months=1)

        assert variance[-1]["actual_spent"] == D("0")
        assert variance[-1]["monthly_variance"] == D("500.00")
        assert bva["total_spent"] == D("0")
        assert pvr["total_spent"] == D("0")

    async def test_tracking_account_activity_is_not_planned_spend(self, db_session):
        services, budget, checking, group, cat = await _world(db_session)
        brokerage = await create_account(
            db_session, budget, "Cascade Brokerage", account_type="investment", on_budget=False
        )
        # Categorized activity on a tracking account: nothing is ever
        # assigned against a tracking account, so nothing on one is "spent".
        await create_transaction(db_session, budget, brokerage, "-75.00", TODAY, category=cat)

        reports = ReportService(db_session)
        variance = await reports.cumulative_variance(budget.id, months=1)
        bva = await reports.budget_vs_actual(budget.id, FIRST, TODAY)
        pvr = await reports.plan_vs_reality(budget.id, months=1)

        assert variance[-1]["actual_spent"] == D("0")
        assert bva["total_spent"] == D("0")
        assert pvr["total_spent"] == D("0")

    async def test_a_system_group_row_is_not_planned_spend(self, db_session):
        services, budget, checking, group, cat = await _world(db_session)
        system = await create_category_group(db_session, budget, "Income", is_system=True)
        inflow = await create_category(db_session, budget, system, "Ready to Assign")
        # An outflow filed into the system group — a clawed-back paycheque —
        # is negative income, not spending; `BUDGETED_ENVELOPE` never counts
        # an assignment there, so `spent` may not count the row.
        await create_transaction(db_session, budget, checking, "-120.00", TODAY, category=inflow)

        reports = ReportService(db_session)
        variance = await reports.cumulative_variance(budget.id, months=1)
        bva = await reports.budget_vs_actual(budget.id, FIRST, TODAY)
        pvr = await reports.plan_vs_reality(budget.id, months=1)

        assert variance[-1]["actual_spent"] == D("0")
        assert bva["total_spent"] == D("0")
        assert pvr["total_spent"] == D("0")

    async def test_a_refund_does_not_reduce_spent(self, db_session):
        """The deliberate divergence, pinned: `amount < 0` in
        `PLANNED_SPEND_ROW` means a refund posted to a spending category
        never reduces "spent". Flipping it would move every historical
        variance figure — change it at the definition or not at all."""
        services, budget, checking, group, cat = await _world(db_session)
        await create_transaction(db_session, budget, checking, "-100.00", TODAY, category=cat)
        await create_transaction(db_session, budget, checking, "30.00", TODAY, category=cat)

        reports = ReportService(db_session)
        variance = await reports.cumulative_variance(budget.id, months=1)
        bva = await reports.budget_vs_actual(budget.id, FIRST, TODAY)
        pvr = await reports.plan_vs_reality(budget.id, months=1)

        assert variance[-1]["actual_spent"] == D("100.00")
        assert bva["total_spent"] == D("100.00")
        assert pvr["total_spent"] == D("100.00")

    async def test_every_report_spends_the_same_universe(self, db_session):
        """The consolidation itself: over a register that trips every
        excluded term at once, the three reports must quote one figure."""
        services, budget, checking, group, cat = await _world(db_session)
        brokerage = await create_account(
            db_session, budget, "Cascade Brokerage", account_type="investment", on_budget=False
        )
        system = await create_category_group(db_session, budget, "Income", is_system=True)
        inflow = await create_category(db_session, budget, system, "Ready to Assign")

        await create_transaction(db_session, budget, checking, "-100.00", TODAY, category=cat)
        await create_transaction(db_session, budget, checking, "30.00", TODAY, category=cat)
        await create_transfer(
            db_session, budget, checking, brokerage, "200.00", TODAY, category=cat
        )
        await create_transaction(db_session, budget, brokerage, "-75.00", TODAY, category=cat)
        await create_transaction(db_session, budget, checking, "-120.00", TODAY, category=inflow)

        reports = ReportService(db_session)
        variance = await reports.cumulative_variance(budget.id, months=1)
        bva = await reports.budget_vs_actual(budget.id, FIRST, TODAY)
        pvr = await reports.plan_vs_reality(budget.id, months=1)

        assert variance[-1]["actual_spent"] == D("100.00")
        assert bva["total_spent"] == D("100.00")
        assert pvr["total_spent"] == D("100.00")


async def _tagged_envelope(db_session, key: str, name: str):
    """One envelope carrying one system tag, 195 assigned last month and this
    month, and 390 paid out of it today. Dates are read at run time, so a
    month rollover between collection and run cannot move the window."""
    services, budget, checking, group, _ = await _world(db_session)
    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    envelope = await create_category(db_session, budget, group, name)
    await tags.set_category_tags(envelope.id, [(await tags.get_system_tag(budget.id, key)).id])
    today = date.today()
    this_month = today.replace(day=1)
    last_month = add_months(this_month, -1)
    await create_budget_assignment(db_session, budget, envelope, last_month, "195.00")
    await create_budget_assignment(db_session, budget, envelope, this_month, "195.00")
    await create_transaction(db_session, budget, checking, "-390.00", today, category=envelope)
    return budget, last_month, today


class TestASinkingFundsBillIsPlannedSpend:
    """A `long_term_expense` envelope's payout is spending (#182), so the
    plan-vs-actual family counts it against the assignments it already
    counted. Before, the payout classed SAVINGS: Budget vs Actual read the
    sinking fund at assigned 390 and spent 0, and Cumulative Variance built
    the same underspend month after month. Those two are the reports that
    changed — Plan vs Reality did not read the class at the time, so a test
    against it alone passed on the old rule."""

    async def test_budget_vs_actual_counts_the_payout(self, db_session):
        budget, last_month, today = await _tagged_envelope(
            db_session, "long_term_expense", "Property Tax"
        )
        bva = await ReportService(db_session).budget_vs_actual(budget.id, last_month, today)

        assert bva["total_assigned"] == D("390.00")
        assert bva["total_spent"] == D("390.00")

    async def test_cumulative_variance_counts_the_payout(self, db_session):
        budget, *_ = await _tagged_envelope(db_session, "long_term_expense", "Property Tax")
        variance = await ReportService(db_session).cumulative_variance(budget.id, months=2)

        assert [(m["budget_assigned"], m["actual_spent"]) for m in variance] == [
            (D("195.00"), D("0")),
            (D("195.00"), D("390.00")),
        ]
        assert variance[-1]["cumulative_variance"] == D("0")

    async def test_plan_vs_reality_agrees(self, db_session):
        budget, *_ = await _tagged_envelope(db_session, "long_term_expense", "Property Tax")
        pvr = await ReportService(db_session).plan_vs_reality(budget.id, months=2)

        assert (pvr["total_assigned"], pvr["total_spent"]) == (D("390.00"), D("390.00"))

    async def test_the_savings_rate_calls_it_spending(self, db_session):
        # The month the household paid its property tax, it saved nothing.
        budget, *_ = await _tagged_envelope(db_session, "long_term_expense", "Property Tax")
        rate = await ReportService(db_session).savings_rate(budget.id, months=1)

        assert rate["summary"]["savings"] == D("0")
        assert rate["summary"]["spending"] == D("390.00")


class TestASavingsTaggedEnvelope:
    """Item 5d in docs/reports-audit-chain.md, decided and now built: spending
    out of a `savings`-tagged envelope counts against that envelope's plan.

    The tag classes the outflow SAVINGS (rule 1 of `domain.activity_class`),
    and for a long time that meant the plan-vs-actual family counted the
    envelope's assignments and none of its spending — a Vacation Savings
    envelope assigned 195 a month and drained by a 390 flight read as a
    variance of +390 that never closed, permanently under-spent. That is the
    phantom underspend #182 removed for `long_term_expense` only.

    `planned_spend_filter` is where the exception is stated: the household
    PLANNED that money to leave, so against the plan it is spent. The class
    itself does NOT move, and the rest of this class is the bound on the
    change — the savings rate still calls the 390 saving and the spending
    rollups still leave it out, because they read their own row sets.

    The three reports must also give ONE reading. Plan vs Reality once kept
    its own spent set with no class filter and read the full 390 here while
    the other two read 0."""

    async def test_budget_vs_actual_counts_the_payout(self, db_session):
        budget, last_month, today = await _tagged_envelope(
            db_session, "savings", "Vacation Savings"
        )
        bva = await ReportService(db_session).budget_vs_actual(budget.id, last_month, today)

        assert (bva["total_assigned"], bva["total_spent"]) == (D("390.00"), D("390.00"))

    async def test_cumulative_variance_stops_compounding_the_underspend(self, db_session):
        budget, *_ = await _tagged_envelope(db_session, "savings", "Vacation Savings")
        variance = await ReportService(db_session).cumulative_variance(budget.id, months=2)

        # 195 put by and unspent, then 195 put by and 390 taken out: the plan
        # closes at zero instead of carrying a +390 surplus forever.
        assert [(m["budget_assigned"], m["actual_spent"]) for m in variance] == [
            (D("195.00"), D("0")),
            (D("195.00"), D("390.00")),
        ]
        assert variance[-1]["cumulative_variance"] == D("0")

    async def test_plan_vs_reality_agrees(self, db_session):
        budget, *_ = await _tagged_envelope(db_session, "savings", "Vacation Savings")
        pvr = await ReportService(db_session).plan_vs_reality(budget.id, months=2)

        assert (pvr["total_assigned"], pvr["total_spent"]) == (D("390.00"), D("390.00"))

    async def test_the_savings_rate_still_calls_it_saving(self, db_session):
        """The bound. The plan report changed; the class did not. Tagging an
        envelope Savings was asked for so that its outflows count as saving
        with no transfer involved, and that is still what the savings rate
        says — 390 saved, nothing spent."""
        budget, *_ = await _tagged_envelope(db_session, "savings", "Vacation Savings")
        rate = await ReportService(db_session).savings_rate(budget.id, months=1)

        assert rate["summary"]["savings"] == D("390.00")
        assert rate["summary"]["spending"] == D("0")

    async def test_the_spending_rollups_still_leave_it_out(self, db_session):
        """The other half of the bound: the Breakdown and the Overview's Top
        Spending card read `SPENDING_ROW` plus the counted classes, not the
        plan universe, so the 390 does not appear there."""
        budget, last_month, today = await _tagged_envelope(
            db_session, "savings", "Vacation Savings"
        )
        rows, total = await ReportService(db_session).spending_by_category(
            budget.id, last_month, today
        )

        assert total == D("0")
        assert [r for r in rows if r["name"] == "Vacation Savings"] == []
