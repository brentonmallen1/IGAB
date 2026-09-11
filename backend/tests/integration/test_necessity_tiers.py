"""The two necessity tiers, and the gap between them.

From a design conversation with the household's second user:

    "cost of living would be anything that comes out of my account on a monthly
     basis that's not discretionary, like utilities, mortgage payment, any debt
     payments, subscriptions, etc. essentials would only be the things that are
     100% necessary, so mortgage payment is in there but subscriptions aren't...
     seeing a report that shows the difference in those two could be a good way
     to identify areas to cut back and save on or things to shed in some kind
     of emergency event"

Before this, both reports read one tag and one class tuple: Cost of Living was
the Essentials table rolled up by group, and its own docstring said so
("Nothing new is queried... Only the rollup is new"). A passing test asserted
the identity. The only difference a user could see between the two screens was
a calendar artifact from three different windows.

**Every `expect` figure here is written by hand.** Deriving them from the
queries would make each assertion a tautology, and the arithmetic is the thing
under test. The amounts are round enough to check on paper.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from igab.domain.activity_class import NecessityTier
from igab.domain.dates import add_months, month_end
from igab.guide.concepts import essentials_since
from igab.guide.detection import GuideDetection
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.report_basics import cost_of_living
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_transfer,
    create_user,
)

D = Decimal


# Dates are read when a test RUNS, from the clock the services read
# (`date.today()`), never at import. A module-level TODAY was fixed at
# collection while `cost_of_living` and `essentials_summary` read the clock at
# run time, so a run collected at 23:59 on a month's last day and executed
# after midnight put every fixture row two months back — outside the months=1
# window — and every served figure read 0.00.
def _today() -> date:
    return date.today()


def _first_of_last_month() -> date:
    return add_months(_today().replace(day=1), -1)


def _last_month() -> date:
    """Day 6 of last month: inside the last complete month whatever today is."""
    return _first_of_last_month() + timedelta(days=5)


@dataclass(frozen=True)
class ExpectedCosts:
    """What this household's two tiers must read, and their difference."""

    cost_of_living: Decimal
    essentials: Decimal
    gap: Decimal


#: Rent 1,200 + Electric 200 are Essential.
#: Streaming 60 is Cost of living but not Essential.
#: The car payment 340 is UNTAGGED and enters by class (DEBT_PRINCIPAL).
#: So: essentials 1,400; cost of living 1,800; gap 400.
EXPECTED = ExpectedCosts(cost_of_living=D("1800.00"), essentials=D("1400.00"), gap=D("400.00"))


async def _household(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    car_loan = await create_account(
        db_session, budget, "Harborstone Auto Loan", account_type="auto_loan", on_budget=False
    )
    bills = await create_category_group(db_session, budget, "Bills")
    fun = await create_category_group(db_session, budget, "Fun")
    debt = await create_category_group(db_session, budget, "Debt")

    rent = await create_category(db_session, budget, bills, "Rent")
    electric = await create_category(db_session, budget, bills, "Electric")
    streaming = await create_category(db_session, budget, fun, "Streaming")
    car = await create_category(db_session, budget, debt, "Car Payment")

    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    by_key = {t.system_key: t for t in await tags.list_for_budget(budget.id)}
    await tags.set_category_tags(rent.id, [by_key["essential"].id])
    await tags.set_category_tags(electric.id, [by_key["essential"].id])
    await tags.set_category_tags(streaming.id, [by_key["cost_of_living"].id])
    # `car` is deliberately untagged.

    last_month = _last_month()
    await create_transaction(db_session, budget, checking, "-1200.00", last_month, category=rent)
    await create_transaction(db_session, budget, checking, "-200.00", last_month, category=electric)
    await create_transaction(db_session, budget, checking, "-60.00", last_month, category=streaming)
    await create_transfer(
        db_session, budget, checking, car_loan, "340.00", last_month, category=car
    )
    return budget, checking, bills, tags, by_key


class TestTheTwoTiers:
    async def test_the_lean_tier_counts_only_what_cannot_be_cut(self, db_session):
        budget, *_ = await _household(db_session)
        repo = TransactionRepository(db_session)
        total, basis = await repo.essential_spend(
            budget.id, _first_of_last_month(), _today(), tier=NecessityTier.ESSENTIAL
        )
        assert -total == EXPECTED.essentials
        assert basis == "tag"

    async def test_the_wide_tier_adds_the_sheddable_and_the_debt(self, db_session):
        budget, *_ = await _household(db_session)
        repo = TransactionRepository(db_session)
        total, basis = await repo.essential_spend(
            budget.id, _first_of_last_month(), _today(), tier=NecessityTier.COST_OF_LIVING
        )
        assert -total == EXPECTED.cost_of_living
        assert basis == "tag"

    async def test_a_debt_payment_needs_no_tag_at_all(self, db_session):
        """The half of the wide tier that arrives by CLASS. "Any debt payments"
        cannot be said by tagging — the sample budget carries a hand-named
        filter for it with a comment saying so — and asking a household to tag
        each loan envelope is how a report stays empty.
        """
        budget, _checking, _bills, tags, by_key = await _household(db_session)
        repo = TransactionRepository(db_session)
        wide, _ = await repo.essential_spend(
            budget.id, _first_of_last_month(), _today(), tier=NecessityTier.COST_OF_LIVING
        )
        lean, _ = await repo.essential_spend(
            budget.id, _first_of_last_month(), _today(), tier=NecessityTier.ESSENTIAL
        )
        # 340 of car payment plus 60 of streaming.
        assert -wide - -lean == EXPECTED.gap

    async def test_the_nesting_is_structural(self, db_session):
        """Essentials ⊆ Cost of Living, and not because a test says so: the
        wide predicate contains the narrow one as a disjunct, so the two cannot
        drift apart. Tagging a category Essential ALONE must still put it in
        both, with no `cost_of_living` tag anywhere near it.
        """
        budget, checking, bills, tags, by_key = await _household(db_session)
        surprise = await create_category(db_session, budget, bills, "Water")
        await tags.set_category_tags(surprise.id, [by_key["essential"].id])
        await create_transaction(
            db_session, budget, checking, "-45.00", _last_month(), category=surprise
        )

        repo = TransactionRepository(db_session)
        wide, _ = await repo.essential_spend(
            budget.id, _first_of_last_month(), _today(), tier=NecessityTier.COST_OF_LIVING
        )
        lean, _ = await repo.essential_spend(
            budget.id, _first_of_last_month(), _today(), tier=NecessityTier.ESSENTIAL
        )
        assert -lean == EXPECTED.essentials + D("45.00")
        assert -wide == EXPECTED.cost_of_living + D("45.00")
        assert -wide >= -lean


class TestTheServedReport:
    async def test_it_serves_both_tiers_and_the_gap(self, db_session):
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=1)

        # months=1 is the last complete month, where the household spent it
        # all, so the averages divide by one (`complete_month_window`). A
        # window through the running month is what made this report quote
        # $2,750 where Essentials quoted $3,000 for the same tag.
        # Hand-computed, not derived.
        assert report["months_averaged"] == 1
        assert report["avg_monthly_cost_of_living"] == EXPECTED.cost_of_living
        assert report["avg_monthly_essentials"] == EXPECTED.essentials
        assert report["avg_monthly_non_essential"] == EXPECTED.gap

    async def test_both_tiers_are_measured_over_one_window(self, db_session):
        """The gap has to be a difference of two figures across the same days.
        Three windows in this family used to be the only visible difference
        between the two screens — a calendar artifact wearing the gap's
        clothes — so this pins that the served figures share one window.
        """
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=1)
        repo = TransactionRepository(db_session)

        # The averaged window: through the last COMPLETE month, which is what
        # both tiers divide by and what both must measure.
        n = report["months_averaged"]
        averaged_end = month_end(report["months"][n - 1])
        lean, _ = await repo.essential_spend(
            budget.id, report["window_start"], averaged_end, tier=NecessityTier.ESSENTIAL
        )
        wide, _ = await repo.essential_spend(
            budget.id,
            report["window_start"],
            averaged_end,
            tier=NecessityTier.COST_OF_LIVING,
        )
        assert report["avg_monthly_essentials"] == -lean / n
        assert report["avg_monthly_cost_of_living"] == -wide / n

    async def test_the_groups_roll_up_the_wide_tier(self, db_session):
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=1)
        by_group = {g["group_name"]: g["total"] for g in report["groups"]}

        assert by_group == {"Bills": D("1400.00"), "Debt": D("340.00"), "Fun": D("60.00")}
        assert sum(by_group.values()) == EXPECTED.cost_of_living
        # And the shares are of the wide total, so they add to 100.
        assert sum(g["share"] for g in report["groups"]) == D("100.00")

    async def test_the_ratios_answer_two_different_questions(self, db_session):
        budget, checking, *_ = await _household(db_session)
        sysgroup = await create_category_group(db_session, budget, "Income", is_system=True)
        inflow = await create_category(db_session, budget, sysgroup, "Ready to Assign")
        payserv = await create_payee(db_session, budget, "Northwind Payserv")
        await create_transaction(
            db_session, budget, checking, "3600.00", _last_month(), payee=payserv, category=inflow
        )

        report = await cost_of_living(db_session, budget.id, months=1)
        # 1,800 of 3,600 is spoken for; 1,400 of it could not be cut.
        assert report["required_ratio"] == D("50.00")
        assert report["essentials_ratio"] == D("38.89")

    async def test_the_ratios_are_the_quotient_of_the_cards_beside_them(self, db_session):
        """Required and the essentials ratio divide the complete-month figures
        the cards show. They used to divide whole-window totals, running month
        included, so a household whose cards read 1,800 spoken for out of
        3,600 taken home saw Required say 42% — and early in a month, with a
        paycheck in and the bills not yet, the gap was tens of points.
        """
        budget, checking, bills, tags, by_key = await _household(db_session)
        sysgroup = await create_category_group(db_session, budget, "Income", is_system=True)
        inflow = await create_category(db_session, budget, sysgroup, "Ready to Assign")
        payserv = await create_payee(db_session, budget, "Northwind Payserv")
        water = await create_category(db_session, budget, bills, "Water")
        await tags.set_category_tags(water.id, [by_key["essential"].id])
        await create_transaction(
            db_session, budget, checking, "3600.00", _last_month(), payee=payserv, category=inflow
        )
        # The running month: a paycheck and an essential bill. The window is
        # complete months, so neither reaches a card, a group, a total or a
        # ratio. Each of the four figures below once had its own reading of the
        # running month; reverting any one of them moves it.
        today = _today()
        await create_transaction(
            db_session, budget, checking, "3600.00", today, payee=payserv, category=inflow
        )
        await create_transaction(db_session, budget, checking, "-1200.00", today, category=water)

        report = await cost_of_living(db_session, budget.id, months=1)
        # Last month is the window: 1,800 spoken for, 1,400 of it essential,
        # 3,600 taken home. Hand-computed, not derived.
        assert report["months_averaged"] == 1
        assert report["avg_monthly_cost_of_living"] == D("1800.00")
        assert report["avg_monthly_essentials"] == D("1400.00")
        assert report["avg_monthly_income"] == D("3600.00")
        bills_group = next(g for g in report["groups"] if g["group_name"] == "Bills")
        assert bills_group["avg_monthly"] == D("1400.00")
        assert bills_group["total"] == D("1400.00")
        # 1,800 / 3,600 and 1,400 / 3,600 — not the whole-window 3,000 / 7,200
        # (41.67) and 2,600 / 7,200 (36.11) the ratios used to divide.
        assert report["required_ratio"] == D("50.00")
        assert report["essentials_ratio"] == D("38.89")


class TestCostOfLivingQuotesTheEssentialsReport:
    """`months=N` means the last N complete months in both reports now.
    Essentials averaged N complete months while Cost of Living averaged the
    N−1 complete ones of a window through today, so the two agreed only when
    spending was flat — and a lumpy month at the far end of the window was in
    one and not the other."""

    async def _rent(self, db_session, *, premium: bool):
        budget = await create_budget(db_session, await create_user(db_session))
        checking = await create_account(db_session, budget, "Harborstone Checking")
        bills = await create_category_group(db_session, budget, "Bills")
        rent = await create_category(db_session, budget, bills, "Rent")
        insurance = await create_category(db_session, budget, bills, "Insurance")
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        essential = await tags.get_system_tag(budget.id, "essential")
        for cat in (rent, insurance):
            await tags.set_category_tags(cat.id, [essential.id])
        this_month = _today().replace(day=1)
        for n in range(1, 13):
            when = add_months(this_month, -n) + timedelta(days=2)
            await create_transaction(db_session, budget, checking, "-3000.00", when, category=rent)
        if premium:
            # A yearly premium in the oldest month of the twelve.
            when = add_months(this_month, -12) + timedelta(days=9)
            await create_transaction(
                db_session, budget, checking, "-1200.00", when, category=insurance
            )
        # And this month's rent, outside both windows.
        await create_transaction(db_session, budget, checking, "-3000.00", _today(), category=rent)
        return budget

    async def test_steady_spending(self, db_session):
        budget = await self._rent(db_session, premium=False)
        col = await cost_of_living(db_session, budget.id, months=12)
        ess = await ReportService(db_session).essentials_summary(budget.id, 12)
        assert col["avg_monthly_essentials"] == ess["monthly_total_average"] == D("3000.00")

    async def test_a_lumpy_month_at_the_far_end(self, db_session):
        # (36,000 + 1,200) / 12 in both. Cost of Living used to read 3,000
        # (the premium's month was outside its window) against 3,100.
        budget = await self._rent(db_session, premium=True)
        col = await cost_of_living(db_session, budget.id, months=12)
        ess = await ReportService(db_session).essentials_summary(budget.id, 12)
        assert col["avg_monthly_essentials"] == ess["monthly_total_average"] == D("3100.00")
        assert (col["window_start"], col["window_end"]) == (
            ess["window_start"],
            ess["window_end"],
        )


class TestTheEmergencyFundStaysLean:
    async def test_the_target_follows_essentials_not_cost_of_living(self, db_session):
        """A deliberate divergence, stated and pinned.

        The emergency fund is sized to the LEAN tier. The household's second
        user's own framing settles it — the wider set is "things to shed in
        some kind of emergency event", so sizing a fund to cover them would be
        saving up to keep paying for the things you would cancel.

        The test exists to stop a later "make these consistent" cleanup from
        silently re-widening the target: the two figures MUST differ here, and
        the essentials family must be the one the fund follows.
        """
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=2)
        summary = await ReportService(db_session).essentials_summary(budget.id, 2)

        assert report["avg_monthly_cost_of_living"] != report["avg_monthly_essentials"]
        # The Essentials report — which sizes the fund — reads the lean tier.
        assert sum(c["total"] for c in summary["categories"]) == EXPECTED.essentials

    async def test_the_figure_that_sizes_the_fund_is_the_lean_one(self, db_session):
        """The table above is not what sizes the fund. The headline is —
        `essentials_90d`, rolling 90 days ÷ 3 — and the reserve, the Emergency
        Coverage headline and the Guide's target all read it. A cleanup that
        gave `essential_spend` the wide tier by default, or passed it there,
        moved every one of them while the table-only pin above stayed green.

        1,400 of essentials in the 90 days is 466.67 a month; the wide tier's
        1,800 would be 600.00. Hand-computed, not derived.
        """
        budget, *_ = await _household(db_session)
        summary = await ReportService(db_session).essentials_summary(budget.id, 1)
        guide = await GuideDetection(db_session).essential_expenses(budget.id)

        assert summary["essentials_90d"] == D("466.67")
        assert guide.value == D("466.67")
        reserve = {r["months"]: r["amount"] for r in summary["reserve"]}
        assert reserve[3] == D("1400.01")

        # And it is below what the wide tier reads over the same 90 days.
        today = _today()
        wide, _ = await TransactionRepository(db_session).essential_spend(
            budget.id, essentials_since(today), today, tier=NecessityTier.COST_OF_LIVING
        )
        assert -wide == EXPECTED.cost_of_living
        assert summary["essentials_90d"] < D("600.00")


async def _rent_and_streaming(db_session, *, tag_streaming: bool):
    """Rent 1,200 and Streaming 60 last month, nothing tagged Essential."""
    last_month = _last_month()
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    bills = await create_category_group(db_session, budget, "Bills")
    rent = await create_category(db_session, budget, bills, "Rent")
    streaming = await create_category(db_session, budget, bills, "Streaming")
    if tag_streaming:
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        col = await tags.get_system_tag(budget.id, "cost_of_living")
        await tags.set_category_tags(streaming.id, [col.id])
    await create_transaction(db_session, budget, checking, "-1200.00", last_month, category=rent)
    await create_transaction(db_session, budget, checking, "-60.00", last_month, category=streaming)
    return budget


class TestEssentialsNeedTheirOwnTag:
    """Each tier picked its "all spending" fallback on its own, so tagging only
    Cost of living left Essentials reading the whole burn rate — larger than
    the tier it sits inside, "could not be cut", and the red "costs more than
    you take home" on spending that could be cut. Unchosen, it is unknown.
    """

    async def test_tagging_only_cost_of_living_leaves_essentials_unknown(self, db_session):
        budget = await _rent_and_streaming(db_session, tag_streaming=True)
        report = await cost_of_living(db_session, budget.id, months=1)

        assert report["tagged"] is True
        assert report["avg_monthly_cost_of_living"] == D("60.00")
        # Before: 1,260.00 "could not be cut" beside a 60.00 cost of living.
        assert report["avg_monthly_essentials"] is None
        assert report["avg_monthly_non_essential"] is None
        assert report["essentials_ratio"] is None

    async def test_with_nothing_tagged_essentials_is_unknown_too(self, db_session):
        budget = await _rent_and_streaming(db_session, tag_streaming=False)
        report = await cost_of_living(db_session, budget.id, months=1)

        assert report["tagged"] is False
        assert report["avg_monthly_cost_of_living"] == D("1260.00")  # the burn rate, said so
        assert report["avg_monthly_essentials"] is None
        assert report["essentials_ratio"] is None


class TestLoanMoneyComingInIsNotACost:
    async def test_loan_proceeds_leave_cost_of_living_alone(self, db_session):
        """Debt principal joins Cost of Living by class, and the class also
        marks money coming IN from a tracked loan. $5,000 of proceeds netted
        against the tier: a negative cost of living, an "Uncategorized" bar of
        -5,000, and a "comfortable" standing for a whole year."""
        budget, checking, *_ = await _household(db_session)
        loan = await create_account(
            db_session, budget, "Cascade Point Personal Loan", account_type="loan", on_budget=False
        )
        await create_transfer(db_session, budget, loan, checking, "5000.00", _last_month())

        report = await cost_of_living(db_session, budget.id, months=1)

        assert report["avg_monthly_cost_of_living"] == EXPECTED.cost_of_living
        assert all(g["total"] >= 0 for g in report["groups"])


async def _drill_world(db_session, owner=None):
    """A household whose groups enter the wide tier by class, per row.

    Auto holds a $340 loan payment (by class) and $80 of fuel (untagged
    spending, outside the tier); Uncategorized holds a $340 loan payment and
    a $75 purchase. Rent is Essential. The bars read Bills 1,200, Auto 340 and
    Uncategorized 340.
    """
    user = owner or await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    loan = await create_account(
        db_session, budget, "Harborstone Auto Loan", account_type="auto_loan", on_budget=False
    )
    bills = await create_category_group(db_session, budget, "Bills")
    auto = await create_category_group(db_session, budget, "Auto")
    rent = await create_category(db_session, budget, bills, "Rent")
    car = await create_category(db_session, budget, auto, "Car")
    await seed_system_tags(db_session, budget.id)
    tags = TagRepository(db_session)
    essential = await tags.get_system_tag(budget.id, "essential")
    await tags.set_category_tags(rent.id, [essential.id])

    last_month = _last_month()
    await create_transaction(db_session, budget, checking, "-1200.00", last_month, category=rent)
    await create_transfer(db_session, budget, checking, loan, "340.00", last_month, category=car)
    await create_transaction(db_session, budget, checking, "-80.00", last_month, category=car)
    await create_transfer(db_session, budget, checking, loan, "340.00", last_month)
    await create_transaction(db_session, budget, checking, "-75.00", last_month)
    return budget


async def _drill(db_session, budget, report, group, *, tier) -> Decimal:
    """The drill a bar opens, as CostOfLivingReport.drillTo sends it."""
    uncategorized = group["group_name"] == "Uncategorized"
    rows, _, _ = await TransactionRepository(db_session).list_for_budget(
        budget.id,
        start_date=report["window_start"],
        end_date=report["window_end"],
        scope="leaf",
        posted_only=True,
        cash_flow_only=True,
        category_ids=None if uncategorized else [UUID(c) for c in group["category_ids"]],
        uncategorized=uncategorized,
        activity_classes=report["counted_classes"],
        necessity_tier=tier,
    )
    return -sum((r.amount for r in rows), Decimal("0"))


class TestTheDrillTotalsItsBar:
    """Membership is per row once debt principal joins by class, so a bar's
    categories and classes alone list rows the bar never counted."""

    async def test_without_the_tier_the_panel_overstates(self, db_session):
        # Pins the mechanism the parameter fixes: the fuel beside the loan
        # payment, and the stray purchase beside the uncategorized one.
        budget = await _drill_world(db_session)
        report = await cost_of_living(db_session, budget.id, months=1)
        by_name = {g["group_name"]: g for g in report["groups"]}

        assert await _drill(db_session, budget, report, by_name["Auto"], tier=None) == D("420.00")
        assert await _drill(db_session, budget, report, by_name["Uncategorized"], tier=None) == D(
            "415.00"
        )

    async def test_with_it_every_bar_opens_its_own_total(self, db_session):
        budget = await _drill_world(db_session)
        report = await cost_of_living(db_session, budget.id, months=1)
        tier = NecessityTier(report["necessity_tier"])

        assert {g["group_name"]: g["total"] for g in report["groups"]} == {
            "Bills": D("1200.00"),
            "Auto": D("340.00"),
            "Uncategorized": D("340.00"),
        }
        for group in report["groups"]:
            assert await _drill(db_session, budget, report, group, tier=tier) == group["total"]

    async def test_the_tier_reaches_the_query_through_the_api(self, api_client, db_session):
        budget = await _drill_world(db_session, api_client.test_user)
        report = await cost_of_living(db_session, budget.id, months=1)
        auto = next(g for g in report["groups"] if g["group_name"] == "Auto")

        resp = await api_client.get(
            f"/api/v1/{budget.id}/transactions",
            params={
                "start_date": report["window_start"].isoformat(),
                "end_date": report["window_end"].isoformat(),
                "scope": "leaf",
                "posted_only": "true",
                "cash_flow_only": "true",
                "category_ids": ",".join(auto["category_ids"]),
                "activity_classes": ",".join(report["counted_classes"]),
                "necessity_tier": report["necessity_tier"],
            },
        )

        assert resp.status_code == 200
        total = -sum(Decimal(str(t["amount"])) for t in resp.json()["transactions"])
        assert total == D("340.00")
