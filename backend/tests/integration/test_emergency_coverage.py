"""The emergency-fund coverage report: a stock measured against a flow.

The Essentials report says what a lean month costs and carries today's runway
as one card's subtitle. This says whether the fund covers that month, and for
how long, over time — the question "am I covered, and is that getting better".

Hand-computed dollars throughout: essentials are a flat $1,000 a month so every
trailing average is exactly $1,000 and each coverage figure can be checked on
paper.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.domain.dates import add_months, month_start
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.emergency_coverage import (
    EmergencyCoverageService,
    coverage_months,
    trailing_average,
)

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()
#: Complete months, oldest first: MONTHS[0] is six months back, MONTHS[5] last.
MONTHS = [add_months(month_start(TODAY), -n) for n in range(6, 0, -1)]


async def _world(db_session, *, fund_name: str = "Emergency Fund"):
    """A budget spending exactly $1,000 of essentials in each complete month,
    with a savings-tagged envelope whose name mentions an emergency — the
    arrangement detection is most confident about."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    bills = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, bills, "Rent")
    goals = await create_category_group(db_session, budget, "Goals")
    fund = await create_category(db_session, budget, goals, fund_name)

    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    by_key = {t.system_key: t for t in await tags.list_for_budget(budget.id)}
    await tags.set_category_tags(rent.id, [by_key["essential"].id])
    await tags.set_category_tags(fund.id, [by_key["savings"].id])

    for month in MONTHS:
        await create_transaction(
            db_session, budget, checking, "-1000.00", month + timedelta(days=4), category=rent
        )
    return services, budget, fund


async def _fund(services, budget, fund, month, amount: str):
    await services.budgets.set_assignment(budget.id, fund.id, month, Decimal(amount))


async def test_coverage_tracks_the_fund_month_by_month(db_session):
    """$1,000 in the third-oldest complete month and $2,000 more two months
    later, against $1,000 of essentials: 1.0, 1.0, 3.0, 3.0."""
    services, budget, fund = await _world(db_session)
    await _fund(services, budget, fund, MONTHS[2], "1000.00")
    await _fund(services, budget, fund, MONTHS[4], "2000.00")

    report = await EmergencyCoverageService(db_session).coverage(budget.id, months=4)

    assert [p["month"] for p in report["series"]] == MONTHS[2:]
    assert [p["fund_balance"] for p in report["series"]] == [
        Decimal("1000.00"),
        Decimal("1000.00"),
        Decimal("3000.00"),
        Decimal("3000.00"),
    ], "assignments carry forward; the fund does not reset each month"
    assert [p["coverage_months"] for p in report["series"]] == [
        Decimal("1.0"),
        Decimal("1.0"),
        Decimal("3.0"),
        Decimal("3.0"),
    ]


async def test_the_target_band_is_served_per_month(db_session):
    """Three months of essentials is not a fixed sum. Serving the band per
    point is the whole reason the second chart exists."""
    services, budget, fund = await _world(db_session)
    await _fund(services, budget, fund, MONTHS[2], "1000.00")

    report = await EmergencyCoverageService(db_session).coverage(budget.id, months=4)
    for point in report["series"]:
        assert point["essentials"] == Decimal("1000.00")
        assert point["target_low"] == Decimal("3000.00")
        assert point["target_high"] == Decimal("6000.00")


async def test_the_headline_is_the_essentials_reports_own_runway(db_session):
    """Quoted, not recomputed: two reports that each divide the same pair of
    numbers are two reports that can disagree."""
    from igab.services.report_service import ReportService

    services, budget, fund = await _world(db_session)
    await _fund(services, budget, fund, MONTHS[4], "3000.00")

    report = await EmergencyCoverageService(db_session).coverage(budget.id, months=4)
    essentials = await ReportService(db_session).essentials_summary(budget.id, 4)

    assert report["coverage_months"] == essentials["runway_months"]
    assert report["fund_balance"] == essentials["emergency_fund_balance"]
    assert report["essentials_monthly"] == essentials["essentials_90d"]


async def test_no_fund_draws_no_line(db_session):
    """A zero series is a claim — "you had nothing all year". The honest
    answer is that the app has not been told what to look at."""
    _, budget, _fund_cat = await _world(db_session, fund_name="Vacation")

    report = await EmergencyCoverageService(db_session).coverage(budget.id, months=4)
    assert report["fund_balance"] is None
    assert report["series"] == []


async def test_nothing_tagged_essential_has_no_denominator(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await seed_system_tags(db_session, budget.id)

    report = await EmergencyCoverageService(db_session).coverage(budget.id, months=4)
    assert report["tagged"] is False
    assert report["coverage_months"] is None


def test_the_trailing_average_uses_what_exists():
    """Dividing three months of spending by three when only one has happened
    halves the denominator and doubles the coverage — a chart that opens on a
    reassuring number it then walks back."""
    totals = [Decimal("300"), Decimal("600"), Decimal("900"), Decimal("1200")]
    assert trailing_average(totals, 0) == Decimal("300.00")
    assert trailing_average(totals, 1) == Decimal("450.00")
    assert trailing_average(totals, 3) == Decimal("900.00")


def test_a_month_with_no_essentials_has_no_answer():
    """Zero coverage is a specific and alarming claim; "no answer" is not."""
    assert coverage_months(Decimal("5000"), Decimal("0")) is None
    assert coverage_months(Decimal("0"), Decimal("1000")) == Decimal("0.0")
