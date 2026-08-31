"""Linking two synced legs closes the holes an unpaired transfer opens.

Every case here is a shape a bank feed actually produces: two accounts, one
movement, two rows that nothing links. The assertions are on Ready to Assign,
because that is where each of them was found.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.transfers import PairableLeg, pair_legs
from igab.services.card_payment import ensure_payment_category

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

MONTH = date(2026, 8, 1)
MOVED = date(2026, 8, 5)


async def _budget_with(session, *, partner_type, partner_on_budget):
    user = await create_user(session)
    budget = await create_budget(session, user)
    checking = await create_account(session, budget, name="Checking", account_type="checking")
    partner = await create_account(
        session, budget, name="Partner", account_type=partner_type, on_budget=partner_on_budget
    )
    # Every path that makes a card account makes its set-aside envelope too
    # (accounts.py, the YNAB importer, the sample generator). Without it the
    # card's set-aside is computed for display but never reaches the envelope
    # term, so the identity this test asserts would not hold — see
    # `_check_card_without_payment_envelope`.
    await ensure_payment_category(session, partner)
    income_group = await create_category_group(session, budget, name="Income", is_system=True)
    income = await create_category(session, budget, income_group, name="Ready to Assign")
    group = await create_category_group(session, budget, name="Everyday")
    envelope = await create_category(session, budget, group, name="Savings Goal")
    await create_transaction(
        session, budget, checking, amount=Decimal("5000"), txn_date=MONTH, category=income
    )
    return budget, checking, partner, envelope


async def _tba(session, budget):
    summary = await make_services(session).budgets.get_budget_summary(budget.id, MONTH)
    return summary.to_be_assigned


async def _two_unpaired_legs(session, budget, checking, partner, envelope, amount="1000"):
    out = await create_transaction(
        session, budget, checking, amount=Decimal(f"-{amount}"), txn_date=MOVED, category=envelope
    )
    inn = await create_transaction(session, budget, partner, amount=Decimal(amount), txn_date=MOVED)
    return out, inn


class TestUnpairedLegsMoveMoneyThatDidNotMove:
    """The diagnosis, pinned. If either of these ever reads 0, the pairing pass
    has stopped being load-bearing and someone should find out why."""

    async def test_an_on_budget_savings_transfer_invents_money(self, db_session) -> None:
        budget, checking, savings, envelope = await _budget_with(
            db_session, partner_type="savings", partner_on_budget=True
        )
        before = await _tba(db_session, budget)
        await _two_unpaired_legs(db_session, budget, checking, savings, envelope)
        assert await _tba(db_session, budget) - before == Decimal("1000")

    async def test_an_off_budget_loan_payment_costs_no_money(self, db_session) -> None:
        """Off-budget accounts touch no Ready to Assign term. Unpaired here is a
        reporting defect — reports read the legs as real income and spending —
        not a money one."""
        budget, checking, loan, envelope = await _budget_with(
            db_session, partner_type="auto_loan", partner_on_budget=False
        )
        before = await _tba(db_session, budget)
        await _two_unpaired_legs(db_session, budget, checking, loan, envelope)
        assert await _tba(db_session, budget) == before


class TestLinkingRestoresTheFigure:
    @pytest.mark.parametrize("partner_type", ["savings", "credit_card"])
    async def test_linking_two_on_budget_legs_leaves_ready_to_assign_alone(
        self, db_session, partner_type: str
    ) -> None:
        budget, checking, partner, envelope = await _budget_with(
            db_session, partner_type=partner_type, partner_on_budget=True
        )
        before = await _tba(db_session, budget)
        out, inn = await _two_unpaired_legs(db_session, budget, checking, partner, envelope)

        services = make_services(db_session)
        await services.transactions.link_legs(
            budget.id, out, inn, clear_categories=[out.id, inn.id]
        )
        assert await _tba(db_session, budget) == before

    async def test_an_off_budget_partner_keeps_the_on_budget_category(self, db_session) -> None:
        """A mortgage payment is real spending and stays budgeted; only the
        rule's forbidden placements are cleared."""
        budget, checking, loan, envelope = await _budget_with(
            db_session, partner_type="auto_loan", partner_on_budget=False
        )
        out, inn = await _two_unpaired_legs(db_session, budget, checking, loan, envelope)
        services = make_services(db_session)
        await services.transactions.link_legs(budget.id, out, inn, clear_categories=[])

        await db_session.refresh(out)
        assert out.category_id == envelope.id
        assert out.transfer_id == inn.id


class TestBothSidesAgree:
    async def test_the_pure_rule_and_the_write_path_name_the_same_clearings(
        self, db_session
    ) -> None:
        """`pair_legs` decides what must be cleared and `link_legs` clears it.
        A drift between them would silently leave a category on an internal
        movement, counting moved money as spent."""
        budget, checking, savings, envelope = await _budget_with(
            db_session, partner_type="savings", partner_on_budget=True
        )
        out, inn = await _two_unpaired_legs(db_session, budget, checking, savings, envelope)
        legs = [
            PairableLeg(
                id=out.id,
                account_id=checking.id,
                on_budget=True,
                date=MOVED,
                amount=out.amount,
                categorized=True,
                category_is_a_guess=True,
            ),
            PairableLeg(
                id=inn.id,
                account_id=savings.id,
                on_budget=True,
                date=MOVED,
                amount=inn.amount,
                categorized=False,
                category_is_a_guess=True,
            ),
        ]
        confident, review = pair_legs(legs, window_days=5)
        assert not review and len(confident) == 1
        assert confident[0].clears_categories == (out.id,)

        services = make_services(db_session)
        await services.transactions.link_legs(
            budget.id, out, inn, clear_categories=confident[0].clears_categories
        )
        await db_session.refresh(out)
        assert out.category_id is None
        assert out.transfer_id == inn.id


class TestLinkedLegsLookHandMade:
    async def test_each_leg_gets_a_payee_naming_the_other_account(self, db_session) -> None:
        """A pair linked by a sync must be indistinguishable from one linked by
        hand — same field set, read from `transfer_link_fields`."""
        budget, checking, savings, envelope = await _budget_with(
            db_session, partner_type="savings", partner_on_budget=True
        )
        out, inn = await _two_unpaired_legs(db_session, budget, checking, savings, envelope)
        services = make_services(db_session)
        await services.transactions.link_legs(budget.id, out, inn, clear_categories=[out.id])
        await db_session.refresh(out)
        await db_session.refresh(inn)
        assert out.transfer_id == inn.id and inn.transfer_id == out.id
        out_payee = await services.transactions.payee_repo.get(out.payee_id)
        in_payee = await services.transactions.payee_repo.get(inn.payee_id)
        assert out_payee.transfer_account_id == savings.id
        assert in_payee.transfer_account_id == checking.id
