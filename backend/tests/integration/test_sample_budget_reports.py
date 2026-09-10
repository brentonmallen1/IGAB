"""What the sample budget actually demonstrates on the reports that read tags.

The generator's other suites check entity counts and the money's shape. This
checks the thing a demo exists for: that opening the app on sample data shows
these reports doing something.

It has caught the failure mode it was written for. Nothing in the sample
carried the `Essential` tag, so five surfaces — the Essentials report, Cost of
Living, the Overview's essentials card, the Guide's emergency-fund target and
the Emergency Fund report — all rendered their "nothing is tagged yet" empty
state on a budget built to show the app off.
"""

from datetime import date
from decimal import Decimal

from igab.repositories.account_repo import AccountRepository
from igab.repositories.budget_filter_repo import BudgetFilterRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.liability_repo import LiabilityRepository
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.reconciliation_repo import ReconciliationRepository
from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.repositories.target_repo import TargetRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.sample_budget.generator import SampleBudgetGenerator
from igab.services.emergency_coverage import EmergencyCoverageService
from igab.services.report_basics import cost_of_living
from igab.services.report_favorites import ReportFavoritesService
from igab.services.report_service import ReportService

from .factories import create_budget, create_user

#: Today, not a fixed date. The essentials family windows on the rolling last
#: 90 days (`ESSENTIALS_WINDOW_DAYS`) while the generator's anchor decides when
#: the data ENDS — so a past anchor leaves the window half outside the data and
#: every figure here reads low for a reason that has nothing to do with the
#: sample. Demo-ready "today" is the promise being checked, the same one
#: `test_endpoint_result_is_demo_ready_today` makes.
ANCHOR = date.today()


async def _generate(session, budget, tier: str):
    await seed_system_tags(session, budget.id)
    generator = SampleBudgetGenerator(
        session,
        budget.id,
        account_repo=AccountRepository(session),
        category_group_repo=CategoryGroupRepository(session),
        category_repo=CategoryRepository(session),
        payee_repo=PayeeRepository(session),
        transaction_repo=TransactionRepository(session),
        assignment_repo=BudgetAssignmentRepository(session),
        tag_repo=TagRepository(session),
        target_repo=TargetRepository(session),
        scheduled_repo=ScheduledTransactionRepository(session),
        reconciliation_repo=ReconciliationRepository(session),
        liability_repo=LiabilityRepository(session),
        tier=tier,
    )
    return await generator.generate(anchor=ANCHOR)


async def _world(db_session, tier: str = "starter"):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    result = await _generate(db_session, budget, tier)
    return budget, result


async def test_the_essentials_family_has_something_to_say(db_session):
    """One tag, five readers. `tagged` False is the empty state on all of
    them, and it was False on both tiers."""
    for tier in ("starter", "full"):
        budget, _ = await _world(db_session, tier)
        report = await ReportService(db_session).essentials_summary(budget.id, 12)

        assert report["tagged"] is True, tier
        assert report["essentials_90d"] > Decimal("1000"), tier
        assert len(report["categories"]) >= 5, tier
        assert all(m["total"] > 0 for m in report["monthly_series"]), tier


async def test_nothing_is_tagged_essential_and_then_not_counted(db_session):
    """Nothing the sample tags Essential may fall outside the counted classes,
    or the demo ships a permanent "tagged and still not counted" note.

    This used to hold by avoidance: `Long-term expense` classified a row as
    SAVINGS while the essentials family counts SPENDING and DEBT_PRINCIPAL, so
    the two tags were mutually exclusive in effect and the sample carried them
    on different categories. The tag no longer overrides classification, so
    Car Insurance and Property Tax now carry BOTH — and this still passes,
    which is the point: the note is empty because the money is counted, not
    because the combination was dodged."""
    for tier in ("starter", "full"):
        budget, _ = await _world(db_session, tier)
        report = await ReportService(db_session).essentials_summary(budget.id, 12)
        assert report["class_excluded"] == [], tier


async def test_the_full_tier_counts_its_mortgage_as_a_cost_of_living(db_session):
    """The case Cost of Living was changed for. A mortgage is the largest
    thing a household cannot cut and its rows classify as DEBT_PRINCIPAL, so
    before `COST_OF_LIVING_CLASSES` it counted for nothing."""
    budget, _ = await _world(db_session, "full")
    report = await ReportService(db_session).essentials_summary(budget.id, 12)

    names = {c["name"] for c in report["categories"]}
    assert any("Mortgage" in n for n in names)
    # The mortgage alone is $2,444/mo, so a report that dropped it would come
    # in under half of this.
    assert report["essentials_90d"] > Decimal("4000")


async def test_the_emergency_fund_report_draws_a_real_line(db_session):
    """Detection finds the envelope, the essentials give it a denominator, and
    the assignments give it a history — all three, or the report is an empty
    state with a link to the Guide."""
    for tier in ("starter", "full"):
        budget, _ = await _world(db_session, tier)
        report = await EmergencyCoverageService(db_session).coverage(budget.id, months=12)

        assert report["fund_balance"] is not None, tier
        assert report["coverage_months"] is not None, tier
        assert len(report["series"]) == 12, tier
        assert all(p["coverage_months"] is not None for p in report["series"]), tier

        # The fund grows across the window — a flat line demonstrates nothing.
        assert report["series"][-1]["fund_balance"] > report["series"][0]["fund_balance"], tier


async def test_the_fund_is_short_of_the_band_so_the_report_has_a_gap_to_show(db_session):
    """A demo where everything is already funded teaches nothing. The sweep
    used to land here, which put the full tier's fund at $43,270 against its
    own $10,000 target — four times its goal, which reads as a bug in the
    generator rather than as a household."""
    budget, _ = await _world(db_session, "full")
    report = await EmergencyCoverageService(db_session).coverage(budget.id, months=12)

    low, _high = report["target_range"]
    assert report["coverage_months"] < low
    assert report["fund_balance"] < report["target_low"]


async def test_the_budget_bar_and_the_reports_scope_have_saved_filters(db_session):
    """Tag-based, so the reports' scope control can resolve one through the
    same `effective_category_ids` the budget page uses."""
    budget, result = await _world(db_session, "full")

    repo = BudgetFilterRepository(db_session)
    filters = await repo.get_all(budget.id)
    assert result.filters == len(filters) >= 3
    assert [f.name for f in filters][:1] == ["Essentials"], "sort_order is the demo's order"

    effective = await repo.effective_category_ids(filters)
    for saved in filters:
        assert effective.get(saved.id), f"{saved.name} resolves to no categories"


async def test_the_reports_nav_opens_with_a_favorites_row(db_session):
    """The Favorites entry appears only once something is starred, so an
    unstarred sample shows no sign the feature is there."""
    budget, result = await _world(db_session, "starter")

    starred = await ReportFavoritesService(db_session).favorites(budget.id)
    assert result.starred_reports == len(starred) >= 2
    assert "emergency-fund" in starred


async def test_the_demo_actually_shows_a_gap(db_session):
    """A demo whose two necessity tiers are identical demonstrates the product
    value not at all — and until the tiers existed they were identical by
    construction, because Cost of Living was the Essentials table rolled up by
    group.

    So the sample has to earn a non-zero gap, and name what is in it:

    - Streaming is tagged Cost of living, not Essential — the poster child.
    - Home Maintenance is a sinking fund a household defers in an emergency.
    - Car Payment carries NO tag at all and enters by activity class, which is
      the half of the tier that needs no tagging.
    """
    budget, _ = await _world(db_session, "full")
    report = await cost_of_living(db_session, budget.id, months=12)

    assert report["avg_monthly_cost_of_living"] > report["avg_monthly_essentials"]
    assert report["avg_monthly_non_essential"] > Decimal("0")

    # The gap is nameable, not just non-zero: the wide tier must reach groups
    # the lean one does not.
    wide_groups = {g["group_name"] for g in report["groups"]}
    lean = await ReportService(db_session).essentials_summary(budget.id, 12)
    lean_groups = {c["group_name"] for c in lean["categories"]}
    assert wide_groups - lean_groups, (
        f"every group in the wide tier is also in the lean one: {sorted(wide_groups)}"
    )


async def test_the_debt_half_of_the_tier_needs_no_tag(db_session):
    """`Car Payment` is deliberately untagged in the sample. Its rows classify
    DEBT_PRINCIPAL, so it reaches Cost of Living by class — which is what makes
    the figure truthful for a household that has tagged nothing yet, and what
    "any debt payments" means when no tag can express it.
    """
    budget, _ = await _world(db_session, "full")
    report = await cost_of_living(db_session, budget.id, months=12)
    lean = await ReportService(db_session).essentials_summary(budget.id, 12)

    wide_names = {cid for g in report["groups"] for cid in g["category_ids"]}
    lean_names = {str(c["category_id"]) for c in lean["categories"]}
    assert wide_names - lean_names, "the wide tier reaches no category the lean one misses"
