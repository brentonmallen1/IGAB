"""An unpaired transfer leg is still one side of a transfer.

A leg with `transfer_id` has a partner row to ask about categories. A leg
WITHOUT one — a transfer payee and no link, which YNAB imports write by the
thousand and `break` leaves behind — used to be treated as a plain row, so
the category rule asked only "is this account on-budget?" and said yes.

On a card that row then counted twice. `CARD_PAYMENT_FROM_CASH` recognises a
payment through the PAYEE, and the category's card-outflow sum recognises
spending through the CATEGORY; an orphan payment leg carrying a category
satisfied both. Set aside fell by the payment while the envelope rose by the
same amount, with the checking account untouched: Ready to Assign rose by
money that had moved nowhere, the state read `paid_ahead`, and every
integrity check stayed green — the reserve identity holds whatever the legs
say, and `_check_transfer_integrity` loads linked legs only.

The rule is `leg_may_carry_category(own, partner)`, resolved through the payee
when there is no link. The off-budget case is the one that must keep working:
a "spending transfer" to a brokerage is real spending, and stays categorized.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.repositories.payee_repo import PayeeRepository
from igab.services.card_payment import ensure_payment_category
from igab.services.transaction_service import TransactionCreate, TransactionUpdate

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

JUL = date(2026, 7, 1)
D = Decimal


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
    await ensure_payment_category(db_session, visa)
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    # The funded side: 1,000 in, 1,000 to Groceries, 500 spent on the card.
    await create_transaction(db_session, budget, checking, "1000.00", date(2026, 7, 1))
    await create_budget_assignment(db_session, budget, groceries, JUL, "1000.00")
    await create_transaction(
        db_session, budget, visa, "-500.00", date(2026, 7, 5), category=groceries
    )
    # The payee an orphan leg would carry: "Transfer : Checking", on the card.
    to_checking = await PayeeRepository(db_session).find_or_create_transfer(
        budget.id, checking.id, checking.name
    )
    await db_session.flush()
    return services, budget, checking, visa, groceries, to_checking


async def _card(services, budget):
    summary = await services.budgets.get_budget_summary(budget.id, JUL)
    return summary.to_be_assigned, summary.cards[0]


class TestAnOrphanPaymentLegOnACard:
    async def test_creating_one_with_a_category_is_refused(self, db_session):
        """The audit's probe. Before: accepted; Set aside 500 → -500 with the
        checking account untouched; TBA 4,000 → 4,500; state `paid_ahead`."""
        services, budget, checking, visa, groceries, to_checking = await _setup(db_session)
        tba_before, card_before = await _card(services, budget)
        assert card_before.set_aside == D("500.00")

        with pytest.raises(InvariantViolation, match="transfer between two budget accounts"):
            await services.transactions.create(
                budget.id,
                TransactionCreate(
                    account_id=visa.id,
                    date=date(2026, 7, 20),
                    amount=D("500.00"),
                    payee_id=to_checking.id,
                    category_id=groceries.id,
                ),
            )

        tba_after, card_after = await _card(services, budget)
        assert tba_after == tba_before
        assert card_after.set_aside == D("500.00")

    async def test_an_inherited_category_is_dropped_rather_than_refused(self, db_session):
        """Auto-categorization fills a blank category from the payee's history.
        A payment leg is not spending, so it takes nothing — and the row is
        still created, because nobody chose the category being refused."""
        services, budget, checking, visa, groceries, to_checking = await _setup(db_session)
        # Teach the payee a category the ordinary way, on the checking side.
        await create_transaction(
            db_session,
            budget,
            checking,
            "-20.00",
            date(2026, 7, 2),
            category=groceries,
            payee=to_checking,
        )
        await db_session.flush()

        row = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=visa.id,
                date=date(2026, 7, 20),
                amount=D("500.00"),
                payee_id=to_checking.id,
            ),
        )
        assert row.category_id is None

    async def test_filing_an_existing_one_into_a_category_is_refused(self, db_session):
        """The register opens the category box on any on-budget row, including
        one rendering "Transfer" — this is the click that produced the money."""
        services, budget, checking, visa, groceries, to_checking = await _setup(db_session)
        row = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=visa.id,
                date=date(2026, 7, 20),
                amount=D("500.00"),
                payee_id=to_checking.id,
                auto_categorize=False,
            ),
        )
        assert row.category_id is None

        with pytest.raises(InvariantViolation, match="transfer between two budget accounts"):
            await services.transactions.update(
                budget.id, row.id, TransactionUpdate(category_id=groceries.id)
            )

    async def test_giving_a_categorized_row_a_transfer_payee_is_refused(self, db_session):
        """The same end state from the other direction."""
        services, budget, checking, visa, groceries, to_checking = await _setup(db_session)
        row = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=visa.id,
                date=date(2026, 7, 20),
                amount=D("500.00"),
                payee_name="Refund Co",
                category_id=groceries.id,
            ),
        )
        assert row.category_id == groceries.id

        with pytest.raises(InvariantViolation, match="transfer between two budget accounts"):
            await services.transactions.update(
                budget.id, row.id, TransactionUpdate(payee_id=to_checking.id)
            )


class TestTheOffBudgetOrphanKeepsItsCategory:
    async def test_a_spending_transfer_to_a_brokerage_is_still_spending(self, db_session):
        """The case that must not regress: money to an off-budget account is
        real spending, and the rule allows a category on the on-budget side
        whether or not the link exists."""
        services, budget, checking, visa, groceries, _ = await _setup(db_session)
        brokerage = await create_account(
            db_session, budget, "Brokerage", account_type="investment", on_budget=False
        )
        to_brokerage = await PayeeRepository(db_session).find_or_create_transfer(
            budget.id, brokerage.id, brokerage.name
        )
        await db_session.flush()

        row = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=date(2026, 7, 20),
                amount=D("-200.00"),
                payee_id=to_brokerage.id,
                category_id=groceries.id,
            ),
        )
        assert row.category_id == groceries.id
