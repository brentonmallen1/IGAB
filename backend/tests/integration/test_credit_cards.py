"""Credit cards leave Ready to Assign — the whole identity, walked.

The branch arithmetic is pinned in tests/unit/test_cards.py; here the real
service walks the scenarios that were verified by hand when the model was
decided (2026-08-28): a funded swipe moves nothing, credit overspending lands
as the card's Uncovered rather than charging Ready to Assign, cash
overspending keeps today's behavior, assigning to the card covers the debt,
and a payment moves reserved cash without touching the figure.
"""

from datetime import date
from decimal import Decimal

from igab.services.card_payment import ensure_payment_category

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

JUL, AUG = date(2026, 7, 1), date(2026, 8, 1)
D = Decimal


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
    linked = await ensure_payment_category(db_session, visa)
    assert linked is not None and linked.linked_account_id == visa.id
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    await create_transaction(db_session, budget, checking, "1000.00", date(2026, 7, 2), category=inflow)
    await db_session.flush()
    return services, budget, checking, visa, linked, groceries


async def _summary(services, budget, month):
    return await services.budgets.get_budget_summary(budget.id, month)


class TestTheIdentity:
    async def test_a_funded_swipe_moves_nothing(self, db_session):
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "150.00")
        before = (await _summary(services, budget, JUL)).to_be_assigned

        await create_transaction(db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries)
        await db_session.flush()

        s = await _summary(services, budget, JUL)
        assert s.to_be_assigned == before == D("850.00")
        card = s.cards[0]
        # Owed 150, and exactly 150 reserved behind it — nothing uncovered.
        assert (card.balance, card.set_aside, card.uncovered) == (D("-150.00"), D("150.00"), D("0"))

    async def test_credit_overspending_is_uncovered_debt_not_a_charge(self, db_session):
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries)
        await db_session.flush()

        july = await _summary(services, budget, JUL)
        # The category shows the overspend (actionable), Ready to Assign
        # reads exactly YNAB's answer: 1000 − 100 assigned.
        groceries_bal = next(b for b in july.category_balances if b.category_id == groceries.id)
        assert groceries_bal.available == D("-50.00")
        assert july.to_be_assigned == D("900.00")

        august = await _summary(services, budget, AUG)
        # The boundary resets the category; the 50 rides on the card.
        assert august.to_be_assigned == D("900.00")
        card = august.cards[0]
        assert (card.set_aside, card.uncovered) == (D("100.00"), D("50.00"))

    async def test_cash_overspending_still_charges_ready_to_assign(self, db_session):
        services, budget, checking, _, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, checking, "-150.00", date(2026, 7, 9), category=groceries
        )
        await db_session.flush()

        assert (await _summary(services, budget, JUL)).to_be_assigned == D("900.00")
        # Cash left the budget: the write-off at the boundary is real.
        assert (await _summary(services, budget, AUG)).to_be_assigned == D("850.00")

    async def test_assigning_to_the_card_covers_the_debt(self, db_session):
        services, budget, _, visa, linked, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries)
        await create_budget_assignment(db_session, budget, linked, AUG, "50.00")
        await db_session.flush()

        s = await _summary(services, budget, AUG)
        assert s.to_be_assigned == D("850.00")
        card = s.cards[0]
        assert (card.set_aside, card.uncovered) == (D("150.00"), D("0"))

    async def test_a_payment_moves_reserved_cash_without_touching_the_figure(self, db_session):
        services, budget, checking, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "150.00")
        await create_transaction(db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries)
        # The payment pair, service-created so the legs link properly.
        from igab.services.transaction_service import TransactionCreate

        await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=date(2026, 7, 25),
                amount=D("-150.00"),
                transfer_account_id=visa.id,
            ),
        )
        await db_session.flush()

        s = await _summary(services, budget, JUL)
        assert s.to_be_assigned == D("850.00")
        card = s.cards[0]
        assert (card.balance, card.set_aside, card.uncovered) == (D("0.00"), D("0.00"), D("0"))

    async def test_mixed_funding_splits_the_writeoff(self, db_session):
        services, budget, checking, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, checking, "-80.00", date(2026, 7, 8), category=groceries
        )
        await create_transaction(db_session, budget, visa, "-70.00", date(2026, 7, 9), category=groceries)
        await db_session.flush()

        # Overspent 50 with 70 on the card: all 50 rides as card debt.
        assert (await _summary(services, budget, JUL)).to_be_assigned == D("900.00")
        august = await _summary(services, budget, AUG)
        assert august.to_be_assigned == D("900.00")
        assert august.cards[0].uncovered == D("50.00")
        assert august.cards[0].set_aside == D("20.00")  # the funded 70 − 50 riding

    async def test_a_cross_month_refund_releases_the_reservation(self, db_session):
        """The Unreleased Reservation, walked through the service: July's
        funded swipe reserves 150; August's refund of it releases the 150.
        The per-month clamp used to discard the release, leaving the reserve
        in the envelope forever and Ready to Assign 150 lower for good."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "150.00")
        await create_transaction(db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries)
        await create_transaction(db_session, budget, visa, "150.00", date(2026, 8, 9), category=groceries)
        await db_session.flush()

        august = await _summary(services, budget, AUG)
        card = august.cards[0]
        # The card owes nothing and reserves nothing — the two agree again.
        assert (card.balance, card.set_aside, card.uncovered) == (D("0.00"), D("0.00"), D("0"))
        # The refund restored the envelope, so: 1000 − 150 groceries − 0 reserve.
        assert august.to_be_assigned == D("850.00")

    async def test_a_refund_of_ridden_spending_pays_down_uncovered(self, db_session):
        """100 funded of a 150 swipe (50 rides as Uncovered); a full refund
        next month releases the funded 100 and the other 50 clears the debt
        through the balance. Nothing is left on either side."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries)
        await create_transaction(db_session, budget, visa, "150.00", date(2026, 8, 9), category=groceries)
        await db_session.flush()

        august = await _summary(services, budget, AUG)
        card = august.cards[0]
        assert (card.balance, card.set_aside, card.uncovered) == (D("0.00"), D("0.00"), D("0"))

    async def test_an_overpayment_carries_as_a_credit_balance(self, db_session):
        """Defect B walked: paying 150 against a 100 reserve reads −50 in
        July AND still −50 in August — the boundary floor used to absorb the
        surplus into Ready to Assign, ratcheting the reserve upward by every
        overpaid month."""
        services, budget, checking, visa, linked, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries)
        from igab.services.transaction_service import TransactionCreate

        await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=date(2026, 7, 25),
                amount=D("-150.00"),
                transfer_account_id=visa.id,
            ),
        )
        await db_session.flush()

        july = await _summary(services, budget, JUL)
        august = await _summary(services, budget, AUG)
        assert july.cards[0].set_aside == D("-50.00")
        assert august.cards[0].set_aside == D("-50.00")
        # And the figure agrees with itself across the boundary: 1000 income
        # − 100 assigned, the credit overspending riding on the card.
        assert july.to_be_assigned == august.to_be_assigned == D("900.00")

    async def test_card_envelopes_stay_out_of_cover_overspent(self, db_session):
        services, budget, checking, visa, linked, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries)
        # Overpay the card so its envelope runs negative — a cards-section
        # state, not overspending Cover Overspent may act on.
        from igab.services.transaction_service import TransactionCreate

        await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=date(2026, 7, 25),
                amount=D("-150.00"),
                transfer_account_id=visa.id,
            ),
        )
        await db_session.flush()

        s = await _summary(services, budget, JUL)
        linked_bal = next(b for b in s.category_balances if b.category_id == linked.id)
        assert linked_bal.is_card_payment
        assert linked_bal.available == D("-50.00")  # paid 150, only 100 funded
        assert s.total_overspent == D("50.00"), "groceries only — the card is not overspending"
        preview = await services.budgets.cover_overspent_preview(budget.id, JUL)
        assert [i.category_id for i in preview.items] == [groceries.id]
