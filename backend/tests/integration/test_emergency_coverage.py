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

from igab.domain.dates import add_months, month_end, month_start
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.emergency_coverage import (
    EmergencyCoverageService,
    coverage_months,
    history_index,
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


async def test_an_account_fund_counts_through_the_last_day_of_each_month(db_session):
    """A point stands for its whole month, the last day included: a deposit
    on the 31st is in that month's balance, not the next one's. The bound is
    `domain.dates.month_end`, where the report once wrote its own two copies
    of "first of next month, less a day" beside it."""
    services, budget, _unfunded_envelope = await _world(db_session)
    hysa = await create_account(
        db_session, budget, "Cascade Point HYSA", account_type="savings", on_budget=False
    )
    await create_transaction(db_session, budget, hysa, "2000.00", month_end(MONTHS[3]))

    report = await EmergencyCoverageService(db_session).coverage(budget.id, months=4)

    assert [p["month"] for p in report["series"]] == MONTHS[2:]
    assert [p["fund_balance"] for p in report["series"]] == [
        Decimal("0.00"),
        Decimal("2000.00"),
        Decimal("2000.00"),
        Decimal("2000.00"),
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


async def test_a_self_reported_fund_reaches_the_newest_point(db_session, api_client):
    """A self-reported figure used to be counted in the headline cards and in
    no series point at all — the chart drew $0 and 0.0 months beneath cards
    reading the real amount.

    `GuideService.set_binding` stamps `as_of` with today, and the series ends
    at the last COMPLETE month, so `as_of <= month_end` was false for every
    point on every chart. Written through the API on purpose: the stamp is
    what made this unreachable, and a hand-built binding row would not have
    reproduced it.
    """
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    bills = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, bills, "Rent")
    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    by_key = {t.system_key: t for t in await tags.list_for_budget(budget.id)}
    await tags.set_category_tags(rent.id, [by_key["essential"].id])
    for month in MONTHS:
        await create_transaction(
            db_session, budget, checking, "-1000.00", month + timedelta(days=4), category=rent
        )
    await db_session.commit()

    # A figure the household typed, with no as-of date.
    resp = await api_client.put(
        f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
        json={"mode": "manual", "entity_ids": {}, "external": True, "external_amount": "4000"},
    )
    assert resp.status_code in (200, 204), resp.text

    # Read through the API too: the binding was written in the client's own
    # transaction, which `db_session` cannot see.
    body = (await api_client.get(f"/api/v1/{budget.id}/reports/emergency-fund")).json()
    last = body["series"][-1]

    assert last["external_counted"] is True
    assert Decimal(str(last["fund_balance"])) == Decimal("4000.00")
    # $4,000 against $1,000 a month of essentials.
    assert Decimal(str(last["coverage_months"])) == Decimal("4.0")
    # Only the newest point: the figure has no history behind it.
    assert [p["external_counted"] for p in body["series"]][:-1] == [False] * (
        len(body["series"]) - 1
    )
    assert Decimal(str(body["fund_balance"])) == Decimal("4000.00")


class TestTheAverageStartsWithTheHistory:
    """The coverage denominator never averages months before the budget
    existed, and "existed" means its first transaction — the start "All time"
    counts from — not its first Essential bill."""

    def test_history_index_finds_the_first_month_of_history(self):
        months = MONTHS[:4]
        assert history_index(months, None) == 0
        assert history_index(months, MONTHS[0] - timedelta(days=40)) == 0
        assert history_index(months, MONTHS[2] + timedelta(days=12)) == 2
        assert history_index(months, MONTHS[5]) == 4  # after every month listed

    def test_the_average_is_cut_at_the_history_not_before_it(self):
        totals = [Decimal("0"), Decimal("0"), Decimal("900"), Decimal("600")]
        # Before the history: nothing to average.
        assert trailing_average(totals, 1, first_data=2) == Decimal("0")
        # At it: that month alone, not 900 / 3.
        assert trailing_average(totals, 2, first_data=2) == Decimal("900.00")
        assert trailing_average(totals, 3, first_data=2) == Decimal("750.00")
        # With the history behind it, the full three months, zeros included.
        assert trailing_average(totals, 3, first_data=0) == Decimal("500.00")

    async def _budget(self, db_session, *, history_from, bills, fund_amount):
        """A budget whose first transaction is `history_from`, with Essential
        rent bills `{month: amount}` and a fund assigned in the last month."""
        services = make_services(db_session)
        budget = await create_budget(db_session, await create_user(db_session))
        checking = await create_account(db_session, budget, "Checking")
        bills_group = await create_category_group(db_session, budget, "Bills")
        rent = await create_category(db_session, budget, bills_group, "Rent")
        coffee = await create_category(db_session, budget, bills_group, "Coffee")
        goals = await create_category_group(db_session, budget, "Goals")
        fund = await create_category(db_session, budget, goals, "Emergency Fund")
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        by_key = {t.system_key: t for t in await tags.list_for_budget(budget.id)}
        await tags.set_category_tags(rent.id, [by_key["essential"].id])
        await tags.set_category_tags(fund.id, [by_key["savings"].id])
        await create_transaction(
            db_session, budget, checking, "-4.00", history_from, category=coffee
        )
        for month, amount in bills.items():
            await create_transaction(
                db_session, budget, checking, f"-{amount}", month + timedelta(days=4), category=rent
            )
        await _fund(services, budget, fund, MONTHS[5], fund_amount)
        return budget

    async def test_a_month_with_no_essential_bill_is_still_history(self, db_session):
        """History from three months back, the first Essential bill last
        month. The first version started the average at the first bill, so
        last month was averaged alone: 900, where the budget's own three
        months say (0 + 0 + 900) / 3."""
        budget = await self._budget(
            db_session,
            history_from=MONTHS[3] + timedelta(days=1),
            bills={MONTHS[5]: "900.00"},
            fund_amount="900.00",
        )

        report = await EmergencyCoverageService(db_session).coverage(budget.id, months=1)

        [point] = report["series"]
        assert point["essentials"] == Decimal("300.00")
        assert point["coverage_months"] == Decimal("3.0")

    async def test_a_young_budgets_newest_point_and_headline_diverge_by_design(self, db_session):
        """The deliberate divergence, pinned. History began last month, with
        $1,000 of essentials and a $2,000 fund. The newest point divides by
        the one month that exists — 2.0 months of runway — while the headline,
        the Guide's 90 days ÷ 3, reads 6.0. Bounded: at most a factor of
        three, and gone once three complete months exist."""
        budget = await self._budget(
            db_session,
            history_from=MONTHS[5] + timedelta(days=1),
            bills={MONTHS[5]: "1000.00"},
            fund_amount="2000.00",
        )

        report = await EmergencyCoverageService(db_session).coverage(budget.id, months=1)

        [point] = report["series"]
        assert point["essentials"] == Decimal("1000.00")
        assert point["coverage_months"] == Decimal("2.0")
        assert report["essentials_monthly"] == Decimal("333.33")
        assert report["coverage_months"] == Decimal("6.0")
        assert point["essentials"] <= report["essentials_monthly"] * 3 + Decimal("0.01")
