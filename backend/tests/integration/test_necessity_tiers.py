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

from igab.domain.activity_class import NecessityTier
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
TODAY = date.today()


def _first_of_last_month() -> date:
    first = TODAY.replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)


LAST_MONTH = _first_of_last_month() + timedelta(days=5)


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

    await create_transaction(db_session, budget, checking, "-1200.00", LAST_MONTH, category=rent)
    await create_transaction(db_session, budget, checking, "-200.00", LAST_MONTH, category=electric)
    await create_transaction(db_session, budget, checking, "-60.00", LAST_MONTH, category=streaming)
    await create_transfer(
        db_session, budget, checking, car_loan, "340.00", LAST_MONTH, category=car
    )
    return budget, checking, bills, tags, by_key


class TestTheTwoTiers:
    async def test_the_lean_tier_counts_only_what_cannot_be_cut(self, db_session):
        budget, *_ = await _household(db_session)
        repo = TransactionRepository(db_session)
        total, basis = await repo.essential_spend(
            budget.id, _first_of_last_month(), TODAY, tier=NecessityTier.ESSENTIAL
        )
        assert -total == EXPECTED.essentials
        assert basis == "tag"

    async def test_the_wide_tier_adds_the_sheddable_and_the_debt(self, db_session):
        budget, *_ = await _household(db_session)
        repo = TransactionRepository(db_session)
        total, basis = await repo.essential_spend(
            budget.id, _first_of_last_month(), TODAY, tier=NecessityTier.COST_OF_LIVING
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
            budget.id, _first_of_last_month(), TODAY, tier=NecessityTier.COST_OF_LIVING
        )
        lean, _ = await repo.essential_spend(
            budget.id, _first_of_last_month(), TODAY, tier=NecessityTier.ESSENTIAL
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
            db_session, budget, checking, "-45.00", LAST_MONTH, category=surprise
        )

        repo = TransactionRepository(db_session)
        wide, _ = await repo.essential_spend(
            budget.id, _first_of_last_month(), TODAY, tier=NecessityTier.COST_OF_LIVING
        )
        lean, _ = await repo.essential_spend(
            budget.id, _first_of_last_month(), TODAY, tier=NecessityTier.ESSENTIAL
        )
        assert -lean == EXPECTED.essentials + D("45.00")
        assert -wide == EXPECTED.cost_of_living + D("45.00")
        assert -wide >= -lean


class TestTheServedReport:
    async def test_it_serves_both_tiers_and_the_gap(self, db_session):
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=2)

        # months=2 over a 2-month window, so a monthly average halves the
        # single month's spending. Hand-computed, not derived.
        assert report["avg_monthly_cost_of_living"] == EXPECTED.cost_of_living / 2
        assert report["avg_monthly_essentials"] == EXPECTED.essentials / 2
        assert report["avg_monthly_non_essential"] == EXPECTED.gap / 2

    async def test_both_tiers_are_measured_over_one_window(self, db_session):
        """The gap has to be a difference of two figures across the same days.
        Three windows in this family used to be the only visible difference
        between the two screens — a calendar artifact wearing the gap's
        clothes — so this pins that the served figures share one window.
        """
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=2)
        repo = TransactionRepository(db_session)

        lean, _ = await repo.essential_spend(
            budget.id, report["window_start"], report["window_end"], tier=NecessityTier.ESSENTIAL
        )
        wide, _ = await repo.essential_spend(
            budget.id,
            report["window_start"],
            report["window_end"],
            tier=NecessityTier.COST_OF_LIVING,
        )
        n = len(report["months"])
        assert report["avg_monthly_essentials"] == -lean / n
        assert report["avg_monthly_cost_of_living"] == -wide / n

    async def test_the_groups_roll_up_the_wide_tier(self, db_session):
        budget, *_ = await _household(db_session)
        report = await cost_of_living(db_session, budget.id, months=2)
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
            db_session, budget, checking, "3600.00", LAST_MONTH, payee=payserv, category=inflow
        )

        report = await cost_of_living(db_session, budget.id, months=2)
        # 1,800 of 3,600 is spoken for; 1,400 of it could not be cut.
        assert report["required_ratio"] == D("50.00")
        assert report["essentials_ratio"] == D("38.89")


class TestTheEmergencyFundStaysLean:
    async def test_the_target_follows_essentials_not_cost_of_living(self, db_session):
        """A deliberate divergence, stated and pinned.

        The emergency fund is sized to the LEAN tier. Derk's own framing
        settles it — the wider set is "things to shed in some kind of emergency
        event", so sizing a fund to cover them would be saving up to keep
        paying for the things you would cancel.

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
