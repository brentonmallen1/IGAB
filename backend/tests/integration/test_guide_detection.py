"""What the Guide infers from a real budget.

Detection decides what the roadmap tells someone about their own money, so the
cases that matter most here are the ones where it should decline to answer:
an unknown interest rate, no income on record, nothing that looks like an
emergency fund. Guessing in those cases is worse than admitting ignorance.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.guide.detection import GuideDetection
from igab.repositories.tag_repo import TagRepository

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_liability,
    create_tag,
    create_transaction,
    create_user,
)

TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)


async def _budget(session):
    user = await create_user(session)
    return await create_budget(session, user)


async def _savings_category(session, budget, name: str, *, tagged: bool = True):
    group = await create_category_group(session, budget, "Savings")
    category = await create_category(session, budget, group, name)
    if tagged:
        tag = await create_tag(session, budget, "Savings", system_key="savings")
        # Category.tags is lazy="noload", so appending would trigger IO outside
        # the greenlet. The repo is how the app does it.
        await TagRepository(session).set_category_tags(category.id, [tag.id])
    return category



async def _contribute(session, budget, from_account, to_account, category, amount, when):
    """A retirement contribution as IGAB actually records one.

    A categorised transfer out of an on-budget account into an off-budget
    asset. That outflow leg is what classifies as SAVINGS — a bare deposit
    *inside* the investment account is investment return, which is deliberately
    not counted as money the household saved.
    """
    inflow = await create_transaction(session, budget, to_account, amount, when)
    outflow = await create_transaction(
        session, budget, from_account, f"-{amount}", when,
        category=category, transfer_id=inflow.id,
    )
    inflow.transfer_id = outflow.id
    await session.flush()
    return outflow


class TestEmergencyFund:
    async def test_prefers_a_savings_tagged_category_named_for_an_emergency(self, db_session):
        budget = await _budget(db_session)
        cat = await _savings_category(db_session, budget, "Emergency Fund")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "1500.00")

        found = await GuideDetection(db_session).emergency_fund(budget.id)

        assert found.met is True
        assert found.value == Decimal("1500.00")
        assert "tagged Savings" in found.reason
        assert found.entities["category"] == [cat.id]

    async def test_matches_rainy_day_and_buffer_too(self, db_session):
        budget = await _budget(db_session)
        cat = await _savings_category(db_session, budget, "Rainy Day")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "800.00")

        found = await GuideDetection(db_session).emergency_fund(budget.id)
        assert found.entities["category"] == [cat.id]

    async def test_spending_reduces_the_balance(self, db_session):
        budget = await _budget(db_session)
        account = await create_account(db_session, budget, account_type="checking")
        cat = await _savings_category(db_session, budget, "Emergency Fund")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "1500.00")
        await create_transaction(db_session, budget, account, "-400.00", TODAY, category=cat)

        found = await GuideDetection(db_session).emergency_fund(budget.id)
        assert found.value == Decimal("1100.00")

    async def test_untagged_name_match_is_reported_with_a_weaker_reason(self, db_session):
        budget = await _budget(db_session)
        cat = await _savings_category(db_session, budget, "Emergency Fund", tagged=False)
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "900.00")

        found = await GuideDetection(db_session).emergency_fund(budget.id)
        assert found.value == Decimal("900.00")
        assert found.reason == "the category name mentions an emergency"

    async def test_falls_back_to_a_savings_account_and_says_so(self, db_session):
        budget = await _budget(db_session)
        account = await create_account(db_session, budget, account_type="savings")
        await create_transaction(db_session, budget, account, "5000.00", TODAY)

        found = await GuideDetection(db_session).emergency_fund(budget.id)

        assert found.value == Decimal("5000.00")
        # The weaker signal must admit it is weaker: a savings account may be
        # holding a house deposit.
        assert "may also be holding other plans" in found.reason
        assert found.entities["account"] == [account.id]

    async def test_admits_when_it_cannot_tell(self, db_session):
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Bills")
        await create_category(db_session, budget, group, "Electric")

        found = await GuideDetection(db_session).emergency_fund(budget.id)

        assert found.met is None
        assert found.value is None
        assert "could not find" in found.reason

    async def test_a_binding_overrides_every_heuristic(self, db_session):
        budget = await _budget(db_session)
        # A category the heuristic would have picked...
        decoy = await _savings_category(db_session, budget, "Emergency Fund")
        await create_budget_assignment(db_session, budget, decoy, THIS_MONTH, "1500.00")
        # ...and the one the user actually means.
        group = await create_category_group(db_session, budget, "Other")
        real = await create_category(db_session, budget, group, "House Cushion")
        await create_budget_assignment(db_session, budget, real, THIS_MONTH, "4000.00")

        found = await GuideDetection(db_session).emergency_fund(
            budget.id, bound={"category": (real.id,)}
        )

        assert found.value == Decimal("4000.00")
        assert found.entities["category"] == [real.id]
        assert "you told us" in found.reason


class TestEssentialExpenses:
    async def test_averages_ninety_days_of_spending(self, db_session):
        budget = await _budget(db_session)
        account = await create_account(db_session, budget, account_type="checking")
        group = await create_category_group(db_session, budget, "Bills")
        cat = await create_category(db_session, budget, group, "Rent")
        for offset in (5, 35, 65):
            await create_transaction(
                db_session, budget, account, "-1200.00", TODAY - timedelta(days=offset), category=cat
            )

        found = await GuideDetection(db_session).essential_expenses(budget.id)
        assert found.value == Decimal("1200.00")

    async def test_ignores_spending_older_than_the_window(self, db_session):
        budget = await _budget(db_session)
        account = await create_account(db_session, budget, account_type="checking")
        group = await create_category_group(db_session, budget, "Bills")
        cat = await create_category(db_session, budget, group, "Rent")
        await create_transaction(
            db_session, budget, account, "-9000.00", TODAY - timedelta(days=200), category=cat
        )

        found = await GuideDetection(db_session).essential_expenses(budget.id)
        assert found.value == Decimal("0.00")

    async def test_bound_categories_narrow_it(self, db_session):
        budget = await _budget(db_session)
        account = await create_account(db_session, budget, account_type="checking")
        group = await create_category_group(db_session, budget, "Spending")
        rent = await create_category(db_session, budget, group, "Rent")
        fun = await create_category(db_session, budget, group, "Dining")
        await create_transaction(db_session, budget, account, "-3000.00", TODAY, category=rent)
        await create_transaction(db_session, budget, account, "-600.00", TODAY, category=fun)

        found = await GuideDetection(db_session).essential_expenses(
            budget.id, bound={"category": (rent.id,)}
        )
        assert found.value == Decimal("1000.00")
        assert "you told us are essential" in found.reason


class TestDebtBands:
    async def test_high_interest_counts_debts_at_ten_or_above(self, db_session):
        budget = await _budget(db_session)
        card = await create_liability(
            db_session, budget, "Visa",
            liability_type="credit_card",
            interest_rate=Decimal("22.9000"),
            manual_balance=Decimal("3410.00"),
        )
        await create_liability(
            db_session, budget, "Car",
            liability_type="auto",
            interest_rate=Decimal("6.4000"),
            manual_balance=Decimal("14200.00"),
        )

        found = await GuideDetection(db_session).high_interest_debt(budget.id)

        assert found.met is True
        assert found.value == Decimal("3410.00")
        assert found.entities["liability"] == [card.id]

    async def test_exactly_ten_percent_counts_as_high(self, db_session):
        # The source chart says "10% or higher", so the boundary is inclusive.
        budget = await _budget(db_session)
        await create_liability(
            db_session, budget, "Store card",
            interest_rate=Decimal("10.0000"), manual_balance=Decimal("500.00"),
        )
        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.value == Decimal("500.00")

    async def test_an_unknown_rate_is_a_gap_not_an_assumption(self, db_session):
        # Terms are optional since companion accounts landed. Assuming a null
        # rate is cheap would drop a 26% card out of the roadmap's key step.
        budget = await _budget(db_session)
        await create_liability(
            db_session, budget, "Unknown card",
            interest_rate=None, minimum_payment=None, manual_balance=Decimal("900.00"),
        )

        found = await GuideDetection(db_session).high_interest_debt(budget.id)

        assert found.met is False
        assert found.value == Decimal("0")
        assert found.gaps == ["Unknown card"]

    async def test_moderate_band_is_four_up_to_but_excluding_ten(self, db_session):
        budget = await _budget(db_session)
        car = await create_liability(
            db_session, budget, "Car", liability_type="auto",
            interest_rate=Decimal("6.4000"), manual_balance=Decimal("14200.00"),
        )
        await create_liability(
            db_session, budget, "Cheap", interest_rate=Decimal("3.0000"),
            manual_balance=Decimal("100.00"),
        )
        await create_liability(
            db_session, budget, "Pricey", interest_rate=Decimal("10.0000"),
            manual_balance=Decimal("100.00"),
        )

        found = await GuideDetection(db_session).moderate_interest_debt(budget.id)
        assert found.entities["liability"] == [car.id]
        assert found.value == Decimal("14200.00")

    async def test_moderate_band_leaves_out_an_unmanaged_mortgage(self, db_session):
        budget = await _budget(db_session)
        await create_liability(
            db_session, budget, "Mortgage", liability_type="mortgage",
            interest_rate=Decimal("5.5000"), manual_balance=Decimal("250000.00"),
        )

        found = await GuideDetection(db_session).moderate_interest_debt(budget.id)
        assert found.met is False
        assert found.entities["liability"] == []

    async def test_a_managed_mortgage_is_recognised_by_its_account_type(self, db_session):
        # A managed liability's kind comes from the account, not liability_type
        # — which is left null for companions. Reading the stored column here
        # would let a mortgage into the moderate band.
        budget = await _budget(db_session)
        account = await create_account(
            db_session, budget, "Home loan", account_type="mortgage", on_budget=False
        )
        await create_transaction(db_session, budget, account, "-250000.00", TODAY)
        await create_liability(
            db_session, budget, "Home loan",
            liability_type=None,
            linked_account_id=account.id,
            interest_rate=Decimal("5.5000"),
        )

        found = await GuideDetection(db_session).moderate_interest_debt(budget.id)
        assert found.entities["liability"] == []

    async def test_a_managed_balance_comes_from_the_ledger(self, db_session):
        budget = await _budget(db_session)
        account = await create_account(
            db_session, budget, "Visa", account_type="credit_card", on_budget=True
        )
        await create_transaction(db_session, budget, account, "-1200.00", TODAY)
        lia = await create_liability(
            db_session, budget, "Visa",
            liability_type=None, linked_account_id=account.id,
            interest_rate=Decimal("22.9000"),
        )

        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.entities["liability"] == [lia.id]
        assert found.value == Decimal("1200.00")

    async def test_a_cleared_debt_is_not_counted(self, db_session):
        budget = await _budget(db_session)
        await create_liability(
            db_session, budget, "Paid off",
            interest_rate=Decimal("19.0000"), manual_balance=Decimal("0"),
        )
        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.met is False

    async def test_no_liabilities_at_all(self, db_session):
        budget = await _budget(db_session)
        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.met is False
        assert found.value == Decimal("0")
        assert found.gaps == []


class TestRetirementContributions:
    async def test_declines_when_there_are_no_investment_accounts(self, db_session):
        budget = await _budget(db_session)
        found = await GuideDetection(db_session).retirement_contributions(budget.id)
        assert found.met is None
        assert found.value is None
        assert "cannot see any retirement accounts" in found.reason

    async def test_declines_when_there_is_no_income_to_divide_by(self, db_session):
        # A rate against zero income is not a small number, it is meaningless.
        budget = await _budget(db_session)
        await create_account(db_session, budget, account_type="investment", on_budget=False)
        found = await GuideDetection(db_session).retirement_contributions(budget.id)
        assert found.met is None
        assert found.value is None
        assert "meaningless" in found.reason

    async def test_says_the_figure_is_a_lower_bound_without_a_binding(self, db_session):
        budget = await _budget(db_session)
        await create_account(db_session, budget, account_type="investment", on_budget=False)
        checking = await create_account(db_session, budget, account_type="checking")
        await create_transaction(db_session, budget, checking, "50000.00", TODAY)

        found = await GuideDetection(db_session).retirement_contributions(budget.id)

        # Honest about the limit: IGAB knows which accounts are investments,
        # not which are for retirement, and never sees a workplace plan.
        assert "tell us which are for retirement" in found.reason

    async def test_computes_the_rate_against_income(self, db_session):
        budget = await _budget(db_session)
        checking = await create_account(db_session, budget, account_type="checking")
        retirement = await create_account(
            db_session, budget, "401k", account_type="investment", on_budget=False
        )
        group = await create_category_group(db_session, budget, "Saving")
        cat = await create_category(db_session, budget, group, "Retirement")
        await create_transaction(db_session, budget, checking, "50000.00", TODAY - timedelta(days=30))
        await _contribute(
            db_session, budget, checking, retirement, cat, "6000.00", TODAY - timedelta(days=20)
        )

        found = await GuideDetection(db_session).retirement_contributions(
            budget.id, bound={"account": (retirement.id,)}
        )

        assert found.value == Decimal("12.00")
        assert "accounts you marked as retirement" in found.reason

    async def test_ignores_contributions_older_than_a_year(self, db_session):
        budget = await _budget(db_session)
        checking = await create_account(db_session, budget, account_type="checking")
        retirement = await create_account(
            db_session, budget, "401k", account_type="investment", on_budget=False
        )
        group = await create_category_group(db_session, budget, "Saving")
        cat = await create_category(db_session, budget, group, "Retirement")
        await create_transaction(db_session, budget, checking, "50000.00", TODAY - timedelta(days=30))
        await _contribute(
            db_session, budget, checking, retirement, cat, "6000.00", TODAY - timedelta(days=400)
        )

        found = await GuideDetection(db_session).retirement_contributions(
            budget.id, bound={"account": (retirement.id,)}
        )
        assert found.value == Decimal("0.00")


@pytest.mark.parametrize(
    "concept",
    ["emergency_fund", "essential_expenses", "high_interest_debt", "moderate_interest_debt"],
)
async def test_every_finding_carries_its_reasoning(db_session, concept):
    # The Guide shows a reason beside every derived figure. A finding without
    # one would render a bare number the app cannot explain.
    budget = await _budget(db_session)
    found = await getattr(GuideDetection(db_session), concept)(budget.id)
    assert found.reason
    assert found.concept_key == concept


class TestTheGuideReadsTheBudgetPagesNumber:
    """The roadmap's figures decide what it tells someone about their money.

    `_category_balance` was `SUM(assigned) + SUM(activity)` over all time —
    no month buckets, no zero floor, no upper bound on the month. Every case
    below produced a different number from the budget page, always lower for
    overspending and higher for pre-assignment, and the emergency-fund verdict
    is decided by comparing this figure against essential expenses.
    """

    async def _category_with_history(self, db_session, budget, history):
        """history: list of (month, assigned, activity)."""
        group = await create_category_group(db_session, budget, "Savings")
        category = await create_category(db_session, budget, group, "Emergency Fund")
        account = await create_account(db_session, budget, "Checking")
        for month, assigned, activity in history:
            if assigned is not None:
                await create_budget_assignment(
                    db_session, budget, category, month, Decimal(assigned)
                )
            if activity is not None:
                await create_transaction(
                    db_session,
                    budget,
                    account,
                    activity,
                    month,
                    category=category,
                    cleared="cleared",
                )
        return category

    async def _both_numbers(self, db_session, budget, category):
        from .factories import make_services

        services = make_services(db_session)
        detection = GuideDetection(db_session)
        guide = await detection._category_balance(budget.id, [category.id])
        page = await services.budgets.get_category_balance(category.id, THIS_MONTH)
        return guide, page.available

    async def test_a_covered_overspend_does_not_follow_the_category_forever(self, db_session):
        # The headline case. January overspent by 50 and TBA covered it, so
        # February starts at zero. A running total says 50 less, permanently.
        budget = await _budget(db_session)
        last = (THIS_MONTH - timedelta(days=1)).replace(day=1)
        category = await self._category_with_history(
            db_session, budget, [(last, "100.00", "-150.00"), (THIS_MONTH, "200.00", None)]
        )

        guide, page = await self._both_numbers(db_session, budget, category)

        assert guide == page == Decimal("200.00")

    async def test_an_assignment_for_a_future_month_is_not_money_you_have_now(self, db_session):
        budget = await _budget(db_session)
        october = (THIS_MONTH + timedelta(days=300)).replace(day=1)
        category = await self._category_with_history(
            db_session, budget, [(THIS_MONTH, "100.00", None), (october, "500.00", None)]
        )

        guide, page = await self._both_numbers(db_session, budget, category)

        assert guide == page == Decimal("100.00")

    async def test_they_agree_on_an_ordinary_history(self, db_session):
        budget = await _budget(db_session)
        last = (THIS_MONTH - timedelta(days=1)).replace(day=1)
        category = await self._category_with_history(
            db_session, budget, [(last, "300.00", "-120.00"), (THIS_MONTH, "150.00", "-40.00")]
        )

        guide, page = await self._both_numbers(db_session, budget, category)

        assert guide == page == Decimal("290.00")

    async def test_the_floor_is_per_category_not_across_the_total(self, db_session):
        # Two categories, one 50 over and one 50 under. Flooring the sum gives
        # 0; flooring each gives 50. The budget page floors each.
        budget = await _budget(db_session)
        last = (THIS_MONTH - timedelta(days=1)).replace(day=1)
        group = await create_category_group(db_session, budget, "Savings")
        account = await create_account(db_session, budget, "Checking")
        over = await create_category(db_session, budget, group, "Over")
        under = await create_category(db_session, budget, group, "Under")
        await create_budget_assignment(db_session, budget, over, last, Decimal("0.00"))
        await create_transaction(
            db_session, budget, account, "-50.00", last, category=over, cleared="cleared"
        )
        await create_budget_assignment(db_session, budget, under, last, Decimal("50.00"))

        detection = GuideDetection(db_session)
        total = await detection._category_balance(budget.id, [over.id, under.id])

        assert total == Decimal("50.00")


class TestTheGuideReadsTheAccountBalanceEveryoneElseReads:
    async def test_a_pending_row_is_not_money_yet(self, db_session):
        budget = await _budget(db_session)
        account = await create_account(db_session, budget, "Savings")
        await create_transaction(db_session, budget, account, "1000.00", TODAY, cleared="cleared")
        await create_transaction(db_session, budget, account, "-900.00", TODAY, cleared="pending")

        from .factories import make_services

        services = make_services(db_session)
        detection = GuideDetection(db_session)

        assert await detection._account_balance([account.id]) == Decimal("1000.00")
        assert await services.account_repo.get_balance(account.id) == Decimal("1000.00")

    async def test_a_split_totals_the_same_either_way(self, db_session):
        # LEAF and PARENT_ROW both get this right; pinned so a future change to
        # BALANCE_ROW cannot quietly start double-counting.
        budget = await _budget(db_session)
        account = await create_account(db_session, budget, "Savings")
        parent = await create_transaction(
            db_session, budget, account, "-100.00", TODAY, cleared="cleared", is_split=True
        )
        for amount in ("-60.00", "-40.00"):
            await create_transaction(
                db_session,
                budget,
                account,
                amount,
                TODAY,
                cleared="cleared",
                parent_transaction_id=parent.id,
            )

        from .factories import make_services

        services = make_services(db_session)
        detection = GuideDetection(db_session)

        assert await detection._account_balance([account.id]) == Decimal("-100.00")
        assert await services.account_repo.get_balance(account.id) == Decimal("-100.00")
