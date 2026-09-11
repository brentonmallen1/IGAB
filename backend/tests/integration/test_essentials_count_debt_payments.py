"""What a month costs includes the mortgage.

Reported by a second household running the app: ten categories tagged
Essential, two in the report, and a mortgage showing a $224 monthly average
against a real payment of $3,000. Nothing was broken about the tag or the
report — the payment is a transfer into a tracked liability account, which
classifies DEBT_PRINCIPAL, and the essentials query counted SPENDING alone.
Tagging the category did nothing at all, and did it silently.

Two rules come out of that, and they pull in opposite directions, which is why
they are pinned together in one file:

- A **spending** report is right to leave debt principal out. Paying down a
  loan moves net worth between columns rather than consuming it, and a
  spending chart that counted it would double-count the purchase it financed.
- A **cost of living** report is wrong to. A household that stops paying its
  mortgage does not keep its house.

So the two diverge deliberately, and `TestTheDivergenceIsDeliberate` fails if
anyone ever makes `COST_OF_LIVING_CLASSES` and `SPENDING_CLASSES` agree.

Figures are round on purpose: $3,000 a month against $400 of groceries reads
on paper, and every assertion here is hand-computed rather than derived from
the query under test.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.domain.activity_class import COST_OF_LIVING_CLASSES, SPENDING_CLASSES, ActivityClass
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_basics import cost_of_living, spending_trends
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
    create_user,
)

D = Decimal
TODAY = date.today()


def _first_of_last_month() -> date:
    first = TODAY.replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)


LAST_MONTH = _first_of_last_month() + timedelta(days=5)


async def _household(db_session):
    """A budget shaped like the report: a mortgage paid into a tracked loan,
    groceries paid from checking, both tagged Essential."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Redwood Checking")
    loan = await create_account(
        db_session,
        budget,
        "Harborstone Mortgage",
        account_type="mortgage",
        on_budget=False,
    )
    group = await create_category_group(db_session, budget, "Housing")
    mortgage = await create_category(db_session, budget, group, "Mortgage")
    groceries = await create_category(db_session, budget, group, "Groceries")

    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    essential = next(
        t for t in await tags.list_for_budget(budget.id) if t.system_key == "essential"
    )
    await tags.set_category_tags(mortgage.id, [essential.id])
    await tags.set_category_tags(groceries.id, [essential.id])

    # The payment: one transfer, cash side categorized. That cash leg is the
    # WHOLE payment — principal, interest and escrow — which is the figure
    # someone means by "my mortgage is $3,000".
    await create_transfer(
        db_session, budget, checking, loan, "3000.00", LAST_MONTH, category=mortgage
    )
    await create_transaction(
        db_session, budget, checking, "-400.00", LAST_MONTH, category=groceries
    )
    return budget, checking, group, mortgage, groceries, tags, essential


class TestTheMortgageIsACostOfLiving:
    async def test_cost_of_living_counts_the_whole_payment(self, db_session):
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=2)

        housing = next(g for g in report["groups"] if g["group_name"] == "Housing")
        # $3,000 + $400, not $400. Before this, the mortgage was simply absent.
        assert housing["total"] == D("3400.00")
        assert report["basis"] == "tag"

    async def test_the_essentials_report_counts_it_too(self, db_session):
        """One query behind all of these, so the figures cannot disagree."""
        budget, *_ = await _household(db_session)
        report = await ReportService(db_session).essentials_summary(budget.id, 2)

        by_name = {c["name"]: c for c in report["categories"]}
        assert by_name["Mortgage"]["total"] == D("3000.00")
        assert by_name["Groceries"]["total"] == D("400.00")

    async def test_the_guides_lean_month_counts_it(self, db_session):
        """The emergency-fund target is measured against this. A fund sized to
        a household's costs must cover the roof over it."""
        budget, *_ = await _household(db_session)
        report = await ReportService(db_session).essentials_summary(budget.id, 2)
        # Rolling 90 days ÷ 3, over one month's activity: 3400 / 3.
        assert report["essentials_90d"] == D("1133.33")

    async def test_the_loan_side_of_the_transfer_is_not_counted_twice(self, db_session):
        """The inflow leg lands on an off-budget account, which every reader
        here excludes. If it were ever counted the total would net to zero and
        the report would say a mortgage costs nothing."""
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=2)
        assert sum(g["total"] for g in report["groups"]) == D("3400.00")


class TestTheDivergenceIsDeliberate:
    """Two rules that must not be quietly reconciled."""

    def test_cost_of_living_counts_more_than_spending_does(self):
        assert SPENDING_CLASSES == (ActivityClass.SPENDING,)
        assert ActivityClass.DEBT_PRINCIPAL in COST_OF_LIVING_CLASSES
        assert set(SPENDING_CLASSES) < set(COST_OF_LIVING_CLASSES)

    def test_interest_is_left_out_on_purpose(self):
        """DEBT_INTEREST only ever classifies on an OFF-budget liability
        account, which every reader here excludes with ON_BUDGET_ACCOUNT.
        Adding it would look like a fix and change nothing — and the cash-side
        transfer already carries the interest anyway."""
        assert ActivityClass.DEBT_INTEREST not in COST_OF_LIVING_CLASSES

    async def test_a_spending_report_still_leaves_the_mortgage_out(self, db_session):
        budget, *_ = await _household(db_session)
        trends = await spending_trends(
            ReportService(db_session), budget.id, LAST_MONTH.replace(day=1), TODAY
        )
        assert Decimal(str(trends["total"])) == D("400.00")


class TestWhatIsStillLeftOutSaysSo:
    """A mortgage is counted now. A category tagged Essential AND Savings is
    not — and silence there would be the same defect wearing a new class."""

    async def test_a_savings_tagged_essential_is_named(self, db_session):
        budget, checking, group, _mortgage, _groceries, tags, essential = await _household(
            db_session
        )
        emergency = await create_category(db_session, budget, group, "Emergency Fund")
        savings_tag = next(
            t for t in await tags.list_for_budget(budget.id) if t.system_key == "savings"
        )
        await tags.set_category_tags(emergency.id, [essential.id, savings_tag.id])
        await create_transaction(
            db_session, budget, checking, "-500.00", LAST_MONTH, category=emergency
        )

        report = await cost_of_living(db_session, budget.id, months=2)
        assert sum(g["total"] for g in report["groups"]) == D("3400.00"), "still not counted"

        note = report["class_excluded"]
        assert [n["activity_class"] for n in note] == [ActivityClass.SAVINGS.value]
        assert note[0]["total"] == D("500.00")
        assert note[0]["categories"] == 1

    async def test_nothing_to_explain_stays_quiet(self, db_session):
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=2)
        assert report["class_excluded"] == []

    async def test_an_untagged_budget_explains_nothing(self, db_session):
        """Nothing tagged means nothing was pointed at, so an absence is not a
        surprise — the report says it is counting everything instead."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Redwood Checking")
        group = await create_category_group(db_session, budget, "Housing")
        cat = await create_category(db_session, budget, group, "Groceries")
        await create_transaction(db_session, budget, checking, "-400.00", LAST_MONTH, category=cat)

        report = await cost_of_living(db_session, budget.id, months=2)
        assert report["basis"] == "all" and report["tagged"] is False
        assert report["class_excluded"] == []


class TestTheReportCanBeOpened:
    """A bar nobody can look inside is indistinguishable from a wrong bar. A
    $30,000 YNAB closing adjustment landing in Uncategorized is what made that
    concrete."""

    async def test_each_group_carries_its_categories(self, db_session):
        budget, _checking, _group, mortgage, groceries, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=2)
        housing = next(g for g in report["groups"] if g["group_name"] == "Housing")
        assert set(housing["category_ids"]) == {str(mortgage.id), str(groceries.id)}

    async def test_the_uncategorized_bucket_carries_none(self, db_session):
        """It is defined by their absence, so it drills by "no category"
        rather than by a list — an empty list filters nothing and would open a
        panel showing the whole window."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Redwood Checking")
        await create_transaction(db_session, budget, checking, "-30000.00", LAST_MONTH)

        report = await cost_of_living(db_session, budget.id, months=2)
        bucket = next(g for g in report["groups"] if g["group_name"] == "Uncategorized")
        assert bucket["total"] == D("30000.00")
        assert bucket["category_ids"] == []

    async def test_the_window_is_served_rather_than_re_derived(self, db_session):
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=2)
        assert report["window_start"] == report["months"][0]
        # The last day of last month: the window is complete months.
        assert report["window_end"] == TODAY.replace(day=1) - timedelta(days=1)

    async def test_the_counted_classes_ride_along(self, db_session):
        """The drill-down passes these on, so the panel totals what the bar
        says instead of every row of the same sign."""
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=2)
        assert report["counted_classes"] == [c.value for c in COST_OF_LIVING_CLASSES]
