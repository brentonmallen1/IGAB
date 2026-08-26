"""The Essentials report, the Overview's essentials card and the Guide's
essential-expenses signal read one query (TransactionRepository.essential_spend*).
Hand-computed dollars throughout.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.guide.detection import GuideDetection
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_service import ReportService
from igab.services.transaction_service import SplitSpec

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()


async def _world(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, group, "Rent")
    fun = await create_category(db_session, budget, group, "Dining")
    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    essential = next(
        t for t in await tags.list_for_budget(budget.id) if t.system_key == "essential"
    )
    return services, budget, checking, rent, fun, tags, essential


def _first_of_last_month() -> date:
    first = TODAY.replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)


async def test_is_empty_without_tags(db_session):
    services, budget, checking, rent, fun, tags, essential = await _world(db_session)
    await create_transaction(db_session, budget, checking, "-1200.00", TODAY, category=rent)

    report = await ReportService(db_session).essentials_summary(budget.id, 6)
    assert report["tagged"] is False
    assert report["categories"] == [] and report["essentials_90d"] == Decimal("0")

    metrics = await ReportService(db_session).dashboard_metrics(
        budget.id, TODAY - timedelta(days=30), TODAY
    )
    assert metrics["essentials_monthly"] is None and metrics["essentials_tagged"] is False


async def test_counts_category_or_payee_tagged_spending(db_session):
    services, budget, checking, rent, fun, tags, essential = await _world(db_session)
    await tags.set_category_tags(rent.id, [essential.id])
    power_co = await create_payee(db_session, budget, "Power Co")
    await tags.set_payee_tags(power_co.id, [essential.id])
    last_month = _first_of_last_month() + timedelta(days=3)
    await create_transaction(db_session, budget, checking, "-1200.00", last_month, category=rent)
    await create_transaction(
        db_session, budget, checking, "-90.00", last_month, category=fun, payee=power_co
    )
    await create_transaction(db_session, budget, checking, "-300.00", last_month, category=fun)

    report = await ReportService(db_session).essentials_summary(budget.id, 1)

    assert report["tagged"] is True
    by_name = {c["name"]: c for c in report["categories"]}
    assert by_name["Rent"]["total"] == Decimal("1200.00")
    assert by_name["Dining"]["total"] == Decimal("90.00"), "payee-tagged, under its own category"
    assert report["monthly_total_average"] == Decimal("1290.00")
    assert [m["total"] for m in report["monthly_series"]] == [Decimal("1290.00")]


async def test_uses_complete_months_only(db_session):
    services, budget, checking, rent, fun, tags, essential = await _world(db_session)
    await tags.set_category_tags(rent.id, [essential.id])
    await create_transaction(
        db_session, budget, checking, "-1200.00", _first_of_last_month(), category=rent
    )
    await create_transaction(db_session, budget, checking, "-1200.00", TODAY, category=rent)

    report = await ReportService(db_session).essentials_summary(budget.id, 1)
    assert report["window_end"] == TODAY.replace(day=1) - timedelta(days=1)
    assert report["categories"][0]["total"] == Decimal("1200.00"), "this month is not counted"


async def test_excludes_transfers_and_savings_classes(db_session):
    services, budget, checking, rent, fun, tags, essential = await _world(db_session)
    savings_cat = await create_category(
        db_session,
        budget,
        (await create_category_group(db_session, budget, "Goals")),
        "Emergency Fund",
    )
    savings_tag = next(
        t for t in await tags.list_for_budget(budget.id) if t.system_key == "savings"
    )
    await tags.set_category_tags(rent.id, [essential.id])
    await tags.set_category_tags(savings_cat.id, [essential.id, savings_tag.id])
    day = _first_of_last_month() + timedelta(days=2)
    await create_transaction(db_session, budget, checking, "-1200.00", day, category=rent)
    await create_transaction(db_session, budget, checking, "-500.00", day, category=savings_cat)
    pending = await create_transaction(
        db_session, budget, checking, "-77.00", day, category=rent, cleared="pending"
    )
    assert pending.cleared == "pending"

    report = await ReportService(db_session).essentials_summary(budget.id, 1)
    assert {c["name"] for c in report["categories"]} == {"Rent"}
    assert report["categories"][0]["total"] == Decimal("1200.00"), "pending and savings excluded"


async def test_split_lines_count_under_their_own_category(db_session):
    services, budget, checking, rent, fun, tags, essential = await _world(db_session)
    await tags.set_category_tags(rent.id, [essential.id])
    day = _first_of_last_month() + timedelta(days=2)
    txn = await create_transaction(db_session, budget, checking, "-100.00", day)
    await services.transactions.convert_to_split(
        budget.id,
        txn.id,
        [
            SplitSpec(amount=Decimal("-60.00"), category_id=rent.id),
            SplitSpec(amount=Decimal("-40.00"), category_id=fun.id),
        ],
    )
    report = await ReportService(db_session).essentials_summary(budget.id, 1)
    assert [(c["name"], c["total"]) for c in report["categories"]] == [("Rent", Decimal("60.00"))]


async def test_reserve_targets_are_one_three_six_twelve_months(db_session):
    services, budget, checking, rent, fun, tags, essential = await _world(db_session)
    await tags.set_category_tags(rent.id, [essential.id])
    for offset in (5, 35, 65):
        await create_transaction(
            db_session, budget, checking, "-1200.00", TODAY - timedelta(days=offset), category=rent
        )

    report = await ReportService(db_session).essentials_summary(budget.id, 12)
    assert report["essentials_90d"] == Decimal("1200.00")
    assert [(r["months"], r["amount"]) for r in report["reserve"]] == [
        (1, Decimal("1200.00")),
        (3, Decimal("3600.00")),
        (6, Decimal("7200.00")),
        (12, Decimal("14400.00")),
    ]
    assert report["roadmap_range"] == (3, 6)


async def test_guide_overview_and_report_agree_on_the_ninety_day_figure(db_session):
    """Three readers, one query: the Guide's signal (and so the emergency-fund
    target), the Overview card and the report headline."""
    services, budget, checking, rent, fun, tags, essential = await _world(db_session)
    await tags.set_category_tags(rent.id, [essential.id])
    for offset in (5, 35, 65):
        await create_transaction(
            db_session, budget, checking, "-1200.00", TODAY - timedelta(days=offset), category=rent
        )
    await create_transaction(
        db_session, budget, checking, "-999.00", TODAY - timedelta(days=5), category=fun
    )

    reports = ReportService(db_session)
    guide = await GuideDetection(db_session).essential_expenses(budget.id)
    metrics = await reports.dashboard_metrics(budget.id, TODAY - timedelta(days=30), TODAY)
    report = await reports.essentials_summary(budget.id, 12)

    assert guide.value == Decimal("1200.00")
    assert metrics["essentials_monthly"] == guide.value and metrics["essentials_tagged"] is True
    assert report["essentials_90d"] == guide.value
    assert "tagged Essential" in guide.reason
