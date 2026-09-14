"""What the Guide infers from a real budget.

Detection decides what the roadmap tells someone about their own money, so the
cases that matter most here are the ones where it should decline to answer:
an unknown interest rate, no income on record, nothing that looks like an
emergency fund. Guessing in those cases is worse than admitting ignorance.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.guide.detection import GuideDetection, liability_service_from
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
    tag_with_system_tags,
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
        session,
        budget,
        from_account,
        f"-{amount}",
        when,
        category=category,
        transfer_id=inflow.id,
    )
    inflow.transfer_id = outflow.id
    await session.flush()
    return outflow


class TestEmergencyFund:
    """The Guide's wrapper over `services.emergency_fund` — what it chose and
    nothing it guessed. The fund's own behaviour is `test_emergency_fund.py`."""

    async def test_reports_what_was_chosen(self, db_session):
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Goals")
        cat = await create_category(db_session, budget, group, "House Cushion")
        await tag_with_system_tags(db_session, cat, "emergency_fund")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "1500.00")

        found = await GuideDetection(db_session).emergency_fund(budget.id)

        assert found.met is True
        assert found.value == Decimal("1500.00")
        assert found.reason == "what you chose to count"
        assert found.entities == {"category": [cat.id]}
        assert found.fund is not None and found.fund.total == Decimal("1500.00")

    async def test_an_empty_chosen_envelope_reports_zero(self, db_session):
        """Zero is an answer when something was chosen — distinct from nothing
        chosen at all."""
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Goals")
        cat = await create_category(db_session, budget, group, "Emergency Fund")
        await tag_with_system_tags(db_session, cat, "emergency_fund")

        found = await GuideDetection(db_session).emergency_fund(budget.id)

        assert found.value == Decimal("0")
        assert found.met is False

    async def test_admits_when_nothing_was_chosen(self, db_session):
        budget = await _budget(db_session)
        cat = await _savings_category(db_session, budget, "Emergency Fund")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "1500.00")

        found = await GuideDetection(db_session).emergency_fund(budget.id)

        assert found.met is None
        assert found.value is None
        assert found.entities == {}
        assert "nothing has been chosen" in found.reason


class TestEssentialExpenses:
    async def test_averages_ninety_days_of_spending(self, db_session):
        budget = await _budget(db_session)
        account = await create_account(db_session, budget, account_type="checking")
        group = await create_category_group(db_session, budget, "Bills")
        cat = await create_category(db_session, budget, group, "Rent")
        for offset in (5, 35, 65):
            await create_transaction(
                db_session,
                budget,
                account,
                "-1200.00",
                TODAY - timedelta(days=offset),
                category=cat,
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

    async def test_an_essential_tag_narrows_detection(self, db_session):
        from igab.repositories.tag_repo import TagRepository, seed_system_tags

        budget = await _budget(db_session)
        account = await create_account(db_session, budget, account_type="checking")
        group = await create_category_group(db_session, budget, "Spending")
        rent = await create_category(db_session, budget, group, "Rent")
        fun = await create_category(db_session, budget, group, "Dining")
        await create_transaction(db_session, budget, account, "-3000.00", TODAY, category=rent)
        await create_transaction(db_session, budget, account, "-600.00", TODAY, category=fun)
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        essential = next(
            t for t in await tags.list_for_budget(budget.id) if t.system_key == "essential"
        )
        await tags.set_category_tags(rent.id, [essential.id])

        found = await GuideDetection(db_session).essential_expenses(budget.id)
        assert found.value == Decimal("1000.00")
        # Categories only: a payee tag counts for nothing, so the Guide must not
        # say it narrowed to the payees someone tagged.
        assert found.reason == "the categories you tagged Essential"

    async def test_a_binding_still_beats_the_tag(self, db_session):
        from igab.repositories.tag_repo import TagRepository, seed_system_tags

        budget = await _budget(db_session)
        account = await create_account(db_session, budget, account_type="checking")
        group = await create_category_group(db_session, budget, "Spending")
        rent = await create_category(db_session, budget, group, "Rent")
        fun = await create_category(db_session, budget, group, "Dining")
        await create_transaction(db_session, budget, account, "-3000.00", TODAY, category=rent)
        await create_transaction(db_session, budget, account, "-600.00", TODAY, category=fun)
        await seed_system_tags(db_session, budget.id)
        tags = TagRepository(db_session)
        essential = next(
            t for t in await tags.list_for_budget(budget.id) if t.system_key == "essential"
        )
        await tags.set_category_tags(rent.id, [essential.id])

        found = await GuideDetection(db_session).essential_expenses(
            budget.id, bound={"category": (fun.id,)}
        )
        assert found.value == Decimal("200.00"), "the user's explicit binding wins"
        assert "you told us are essential" in found.reason


class TestDebtBands:
    async def test_high_interest_counts_debts_at_ten_or_above(self, db_session):
        budget = await _budget(db_session)
        card = await create_liability(
            db_session,
            budget,
            "Visa",
            liability_type="credit_card",
            interest_rate=Decimal("22.9000"),
            manual_balance=Decimal("3410.00"),
        )
        await create_liability(
            db_session,
            budget,
            "Car",
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
            db_session,
            budget,
            "Store card",
            interest_rate=Decimal("10.0000"),
            manual_balance=Decimal("500.00"),
        )
        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.value == Decimal("500.00")

    async def test_an_unknown_rate_is_a_gap_not_an_assumption(self, db_session):
        # Terms are optional since companion accounts landed. Assuming a null
        # rate is cheap would drop a 26% card out of the roadmap's key step.
        budget = await _budget(db_session)
        await create_liability(
            db_session,
            budget,
            "Unknown card",
            interest_rate=None,
            minimum_payment=None,
            manual_balance=Decimal("900.00"),
        )

        found = await GuideDetection(db_session).high_interest_debt(budget.id)

        assert found.met is False
        assert found.value == Decimal("0")
        assert found.gaps == ["Unknown card"]

    async def test_moderate_band_is_four_up_to_but_excluding_ten(self, db_session):
        budget = await _budget(db_session)
        car = await create_liability(
            db_session,
            budget,
            "Car",
            liability_type="auto",
            interest_rate=Decimal("6.4000"),
            manual_balance=Decimal("14200.00"),
        )
        await create_liability(
            db_session,
            budget,
            "Cheap",
            interest_rate=Decimal("3.0000"),
            manual_balance=Decimal("100.00"),
        )
        await create_liability(
            db_session,
            budget,
            "Pricey",
            interest_rate=Decimal("10.0000"),
            manual_balance=Decimal("100.00"),
        )

        found = await GuideDetection(db_session).moderate_interest_debt(budget.id)
        assert found.entities["liability"] == [car.id]
        assert found.value == Decimal("14200.00")

    async def test_moderate_band_leaves_out_an_unmanaged_mortgage(self, db_session):
        budget = await _budget(db_session)
        await create_liability(
            db_session,
            budget,
            "Mortgage",
            liability_type="mortgage",
            interest_rate=Decimal("5.5000"),
            manual_balance=Decimal("250000.00"),
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
            db_session,
            budget,
            "Home loan",
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
            db_session,
            budget,
            "Visa",
            liability_type=None,
            linked_account_id=account.id,
            interest_rate=Decimal("22.9000"),
        )

        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.entities["liability"] == [lia.id]
        assert found.value == Decimal("1200.00")

    async def test_a_cleared_debt_is_not_counted(self, db_session):
        budget = await _budget(db_session)
        await create_liability(
            db_session,
            budget,
            "Paid off",
            interest_rate=Decimal("19.0000"),
            manual_balance=Decimal("0"),
        )
        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.met is False

    async def test_no_liabilities_at_all(self, db_session):
        budget = await _budget(db_session)
        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.met is False
        assert found.value == Decimal("0")
        assert found.gaps == []

    # The four below are named for the ways a copy of the liabilities page's
    # balance rule, kept here, had drifted from it. There is one rule now.

    async def test_a_pending_charge_is_not_debt_yet(self, db_session):
        # BALANCE_ROW leaves pending auth holds out everywhere else in the app;
        # the copy summed NOT_DELETED + LEAF and counted them.
        budget = await _budget(db_session)
        account = await create_account(
            db_session, budget, "Visa", account_type="credit_card", on_budget=True
        )
        await create_transaction(db_session, budget, account, "-1200.00", TODAY)
        await create_transaction(db_session, budget, account, "-300.00", TODAY, cleared="pending")
        await create_liability(
            db_session,
            budget,
            "Visa",
            liability_type=None,
            linked_account_id=account.id,
            interest_rate=Decimal("22.9000"),
        )

        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.value == Decimal("1200.00")

    async def test_an_overpaid_loan_is_not_debt(self, db_session):
        # abs() of a positive balance read an overpayment as money owed.
        budget = await _budget(db_session)
        account = await create_account(
            db_session, budget, "Visa", account_type="credit_card", on_budget=True
        )
        await create_transaction(db_session, budget, account, "50.00", TODAY)
        await create_liability(
            db_session,
            budget,
            "Visa",
            liability_type=None,
            linked_account_id=account.id,
            interest_rate=Decimal("22.9000"),
        )

        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.met is False
        assert found.entities["liability"] == []
        assert found.value == Decimal("0")

    async def test_an_empty_register_keeps_its_manual_balance(self, db_session):
        # A card freshly linked to a transaction-less account must not read as
        # paid off — the liabilities page falls back to the manual balance.
        budget = await _budget(db_session)
        account = await create_account(
            db_session, budget, "Store card", account_type="credit_card", on_budget=True
        )
        await create_liability(
            db_session,
            budget,
            "Store card",
            liability_type=None,
            linked_account_id=account.id,
            interest_rate=Decimal("26.0000"),
            manual_balance=Decimal("890.00"),
        )

        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        assert found.value == Decimal("890.00")

    async def test_the_guide_and_the_liabilities_page_quote_one_balance(self, db_session):
        budget = await _budget(db_session)
        account = await create_account(
            db_session, budget, "Visa", account_type="credit_card", on_budget=True
        )
        await create_transaction(db_session, budget, account, "-1200.00", TODAY)
        await create_transaction(db_session, budget, account, "25.00", TODAY)
        await create_transaction(db_session, budget, account, "-300.00", TODAY, cleared="pending")
        lia = await create_liability(
            db_session,
            budget,
            "Visa",
            liability_type=None,
            linked_account_id=account.id,
            interest_rate=Decimal("22.9000"),
        )

        found = await GuideDetection(db_session).high_interest_debt(budget.id)
        page = await liability_service_from(db_session).get_balance(lia)
        assert found.value == page == Decimal("1175.00")


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
        await create_transaction(
            db_session, budget, checking, "50000.00", TODAY - timedelta(days=30)
        )
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
        await create_transaction(
            db_session, budget, checking, "50000.00", TODAY - timedelta(days=30)
        )
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
