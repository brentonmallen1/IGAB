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

import pytest
from sqlalchemy import select

from igab.db.models import Category, CategoryGroup
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.card_payment import ensure_payment_category

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_liability,
    create_transaction,
    create_user,
    make_services,
)
from .invariants import assert_card_reserve_identity

JUL, AUG, SEP, OCT = (date(2026, m, 1) for m in (7, 8, 9, 10))
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
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=inflow
    )
    await db_session.flush()
    return services, budget, checking, visa, linked, groceries


async def _summary(services, budget, month):
    return await services.budgets.get_budget_summary(budget.id, month)


async def _income_category(db_session, budget):
    """`_setup`'s seeded Ready-to-Assign envelope — the one place a paycheque
    goes, and the one a rewards credit on a card is reasonably filed to."""
    result = await db_session.execute(
        select(Category)
        .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
        .where(Category.budget_id == budget.id, CategoryGroup.is_system == True)  # noqa: E712
    )
    return result.scalars().one()


class TestTheIdentity:
    async def test_a_funded_swipe_moves_nothing(self, db_session):
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "150.00")
        before = (await _summary(services, budget, JUL)).to_be_assigned

        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
        await db_session.flush()

        s = await _summary(services, budget, JUL)
        assert s.to_be_assigned == before == D("850.00")
        card = s.cards[0]
        # Owed 150, and exactly 150 reserved behind it — nothing uncovered.
        assert (card.balance, card.set_aside, card.uncovered) == (D("-150.00"), D("150.00"), D("0"))

    async def test_credit_overspending_is_uncovered_debt_not_a_charge(self, db_session):
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
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
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
        await create_budget_assignment(db_session, budget, linked, AUG, "50.00")
        await db_session.flush()

        s = await _summary(services, budget, AUG)
        assert s.to_be_assigned == D("850.00")
        card = s.cards[0]
        assert (card.set_aside, card.uncovered) == (D("150.00"), D("0"))

    async def test_a_payment_moves_reserved_cash_without_touching_the_figure(self, db_session):
        services, budget, checking, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "150.00")
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
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
        await create_transaction(
            db_session, budget, visa, "-70.00", date(2026, 7, 9), category=groceries
        )
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
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "150.00", date(2026, 8, 9), category=groceries
        )
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
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "150.00", date(2026, 8, 9), category=groceries
        )
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
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
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

    async def test_a_settled_closed_card_sends_no_row(self, db_session):
        """One list used to serve two purposes: include closed cards in the
        sums (right — closing moves no money) and draw a row per card
        (wrong for a card with nothing left to say). Settled + closed →
        no row; anything left → the row stays, tagged."""
        services, budget, checking, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "150.00")
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
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
        await services.account_repo.update(visa.id, is_closed=True)
        await db_session.flush()

        s = await _summary(services, budget, JUL)
        assert s.cards == []
        # And the figure is exactly what it was before the close.
        assert s.to_be_assigned == D("850.00")

    async def test_a_closed_card_with_debt_keeps_its_row_tagged(self, db_session):
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
        await services.account_repo.update(visa.id, is_closed=True)
        await db_session.flush()

        before_close_tba = D("900.00")  # 1000 income − 100 assigned
        august = await _summary(services, budget, AUG)
        assert august.to_be_assigned == before_close_tba
        card = august.cards[0]
        assert card.is_closed
        assert (card.set_aside, card.uncovered) == (D("100.00"), D("50.00"))

    async def test_a_flagged_deleted_account_leaves_both_sides_of_the_figure(self, db_session):
        """The latent filter gap: `soft_delete` cascades transactions today,
        so the two sides agreed by accident. Flag the account row directly —
        the path a future caller might take — and the balance term and the
        activity term must drop together, leaving only the assignment."""
        services, budget, checking, _, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, checking, "-100.00", date(2026, 7, 9), category=groceries
        )
        await db_session.flush()
        assert (await _summary(services, budget, JUL)).to_be_assigned == D("900.00")

        checking.is_deleted = True
        await db_session.flush()
        s = await _summary(services, budget, JUL)
        # Cash term 0 (account gone) and its activity gone with it: the
        # envelope holds the untouched 100 assignment, so 0 − 100.
        assert s.to_be_assigned == D("-100.00")
        groceries_bal = next(b for b in s.category_balances if b.category_id == groceries.id)
        assert groceries_bal.activity == D("0")
        assert groceries_bal.available == D("100.00")

    async def test_card_envelopes_stay_out_of_cover_overspent(self, db_session):
        services, budget, checking, visa, linked, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
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
        assert linked.id not in [i.category_id for i in preview.items]
        # Groceries is absent too, for the other reason: its whole 50 was
        # swiped on the card, so it is credit overspending and Cover
        # Overspent has nothing to fund. The mixed case is the test below.
        assert preview.items == []
        assert preview.total_overspent == D("0")
        assert preview.total_overspent_credit == D("50.00")

    async def test_cover_overspent_offers_the_cash_part_and_not_the_credit_part(self, db_session):
        """The split, through the dialog that spends real money on it.

        Overspent 50 with 20 of it swiped on the card: 30 is cash the
        boundary will write off from Ready to Assign, and 20 rode onto the
        card, where it is already counted in Uncovered. Assigning cash to
        that 20 buys nothing — the debt stays and the envelope floors to
        zero regardless — so the dialog offers 30.

        The glossary has promised exactly this since the credit model
        shipped ("Cover Overspent handles only the cash kind, on purpose").
        Until this test, only the glossary said it: the predicate read
        `-available` and offered the whole 50.
        """
        services, budget, checking, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, checking, "-130.00", date(2026, 7, 8), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "-20.00", date(2026, 7, 9), category=groceries
        )
        await db_session.flush()

        s = await _summary(services, budget, JUL)
        bal = next(b for b in s.category_balances if b.category_id == groceries.id)
        assert bal.available == D("-50.00")
        assert bal.credit_overspent == D("20.00")
        assert (s.total_overspent, s.total_overspent_cash, s.total_overspent_credit) == (
            D("50.00"),
            D("30.00"),
            D("20.00"),
        )
        assert (s.overspent_count, s.overspent_count_cash) == (1, 1)

        preview = await services.budgets.cover_overspent_preview(budget.id, JUL)
        assert [(i.category_id, i.overspent) for i in preview.items] == [(groceries.id, D("30.00"))]
        assert preview.total_overspent == D("30.00")
        assert preview.total_overspent_credit == D("20.00")

    async def test_filing_a_card_charge_does_not_move_ready_to_assign(self, db_session):
        """The claim the interface makes in words, pinned in code.

        Filing a card charge splits three ways that cancel: the part the
        envelope covers raises the card's set-aside (itself in the envelope
        total), the part it cannot is subtracted as `uncovered_current`, and
        the envelope's own fall raises the figure by the whole charge. Sum:
        zero — whatever state the envelope was in, and whatever month the
        charge is dated.

        This is why categorizing months of imported card history is free. It
        only moves red from invisible (the card's Uncovered) to visible (a
        named envelope) — the number on screen grows and nothing is owed
        that was not owed before.
        """
        for name, assigned, prior_cash, charge, charge_date in [
            ("surplus", "150.00", None, "-40.00", date(2026, 7, 9)),
            ("crossing zero", "50.00", None, "-90.00", date(2026, 7, 9)),
            ("already negative", "50.00", "-80.00", "-40.00", date(2026, 7, 9)),
            ("a past month", "50.00", None, "-40.00", date(2026, 6, 9)),
        ]:
            services, budget, checking, visa, _, groceries = await _setup(db_session)
            await create_budget_assignment(db_session, budget, groceries, JUL, assigned)
            if prior_cash:
                await create_transaction(
                    db_session, budget, checking, prior_cash, date(2026, 7, 8), category=groceries
                )
            await db_session.flush()
            before = await _summary(services, budget, JUL)

            await create_transaction(
                db_session, budget, visa, charge, charge_date, category=groceries
            )
            await db_session.flush()
            after = await _summary(services, budget, JUL)

            assert after.to_be_assigned == before.to_be_assigned, name
            assert after.total_overspent_cash == before.total_overspent_cash, name


class TestNothingIsFiledToACardEnvelope:
    """A card's set-aside envelope takes assignments, never transactions.

    `get_budget_summary` overwrites that envelope's balance from card
    arithmetic, so a filed row shows in no envelope, no total, and no red —
    the money simply leaves the budget. The register's category dropdown
    offered it (a card envelope is not hidden; only its group is), so this
    was reachable in the most-used control in the app.
    """

    async def test_creating_a_row_there_is_refused(self, db_session):
        from igab.domain.exceptions import InvariantViolation
        from igab.services.transaction_service import TransactionCreate

        services, budget, checking, _, linked, _ = await _setup(db_session)
        with pytest.raises(InvariantViolation, match="payment envelope"):
            await services.transactions.create(
                budget.id,
                TransactionCreate(
                    account_id=checking.id,
                    date=date(2026, 7, 9),
                    amount=D("-40.00"),
                    category_id=linked.id,
                ),
            )

    async def test_repointing_an_existing_row_there_is_refused(self, db_session):
        from igab.domain.exceptions import InvariantViolation
        from igab.services.transaction_service import TransactionUpdate

        services, budget, checking, _, linked, groceries = await _setup(db_session)
        txn = await create_transaction(
            db_session, budget, checking, "-40.00", date(2026, 7, 9), category=groceries
        )
        await db_session.flush()
        with pytest.raises(InvariantViolation, match="payment envelope"):
            await services.transactions.update(
                budget.id, txn.id, TransactionUpdate(category_id=linked.id)
            )

    async def test_a_split_line_there_is_refused(self, db_session):
        from igab.domain.exceptions import InvariantViolation
        from igab.services.transaction_service import SplitSpec

        services, budget, checking, _, linked, groceries = await _setup(db_session)
        txn = await create_transaction(db_session, budget, checking, "-100.00", date(2026, 7, 9))
        await db_session.flush()
        with pytest.raises(InvariantViolation, match="payment envelope"):
            await services.transactions.convert_to_split(
                budget.id,
                txn.id,
                [
                    SplitSpec(amount=D("-60.00"), category_id=groceries.id),
                    SplitSpec(amount=D("-40.00"), category_id=linked.id),
                ],
            )

    async def test_a_liability_envelope_is_still_assignable(self, db_session):
        """The exclusion names the card term, not `LINKED`: a debt category
        owned by a liability is an ordinary envelope you budget into, and
        the liability screen needs its current binding offered back."""
        services, budget, _, _, linked, groceries = await _setup(db_session)
        liability = await create_liability(
            db_session, budget, "Car loan", manual_balance=D("-5000.00")
        )
        groceries.linked_liability_id = liability.id
        await db_session.flush()

        rows = await services.category_repo.get_all(budget.id, include_archived=True)
        by_id = {c.id: c for c in rows}
        assert by_id[groceries.id].is_assignable is True
        assert by_id[groceries.id].is_categorizable is False
        assert by_id[linked.id].is_assignable is False

    async def test_auto_categorization_never_inherits_a_card_envelope(self, db_session):
        """The caller's category is validated, then auto-categorization
        resolves one afterwards — so the payee's history and default are the
        two ways an unvalidated category reaches the row. One bad historical
        row would otherwise re-file every future transaction for that payee
        into money the budget cannot show."""
        from igab.services.transaction_service import TransactionCreate

        services, budget, checking, _, linked, _ = await _setup(db_session)
        payee = await services.payee_repo.find_or_create(budget.id, "Card Company")
        # A bad row from before the guard existed, written behind the service.
        bad = await create_transaction(
            db_session, budget, checking, "-10.00", date(2026, 7, 1), payee=payee
        )
        bad.category_id = linked.id
        payee.default_category_id = linked.id
        await db_session.flush()

        txn = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=date(2026, 7, 20),
                amount=D("-12.00"),
                payee_id=payee.id,
            ),
        )
        assert txn.category_id is None, "inherited a card envelope past the guard"


class TestTheRefusedRepayment:
    """A card inflow now lands somewhere in every case, and never as red.

    The counterweight this replaces refused any release beyond what a category
    had *funded* on that card, then subtracted the refusal — cumulatively,
    since inception — from a floored carryover balance. On a real budget that
    reached a five-figure overspend on one envelope charging a card that owed
    almost nothing, and it could only grow.
    """

    async def test_a_refund_of_wholly_ridden_spending_leaves_no_trace(self, db_session):
        """Nothing assigned, so July's whole charge rides as Uncovered. August's
        repayment of it discharges the debt: the card is square, the envelope is
        at zero, and Ready to Assign never moved.

        Before: the release was refused (the category had reserved nothing), so
        the envelope was charged a second time for the same shortfall."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "100.00", date(2026, 8, 9), category=groceries
        )
        await db_session.flush()

        august = await _summary(services, budget, AUG)
        card = august.cards[0]
        assert (card.balance, card.set_aside, card.uncovered) == (D("0.00"), D("0.00"), D("0"))
        row = next(b for b in august.category_balances if b.category_id == groceries.id)
        assert row.available == D("0.00")
        assert row.repaid_uncovered_debt == D("100.00")
        # Nothing overspent, so nothing for Cover Overspent to offer.
        assert august.total_overspent == D("0") and august.overspent_count == 0
        assert august.to_be_assigned == D("1000.00")

    async def test_a_card_correction_does_not_outlive_the_month_boundary(self, db_session):
        """The 31x test. July rides 100, August repays it, September overspends
        100 in cash. The correction belongs to August; the old rule kept
        subtracting it from every month after, forever."""
        services, budget, checking, visa, _, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "100.00", date(2026, 8, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, checking, "-100.00", date(2026, 9, 9), category=groceries
        )
        await db_session.flush()

        def row(summary):
            return next(b for b in summary.category_balances if b.category_id == groceries.id)

        assert row(await _summary(services, budget, AUG)).available == D("0.00")
        # September's own red is its own cash overspending, not August's again.
        assert row(await _summary(services, budget, SEP)).available == D("-100.00")
        # And October, which has nothing of its own, is clean. The old rule
        # showed -100 here and in every month after it.
        october = await _summary(services, budget, OCT)
        assert row(october).available == D("0.00")
        assert october.total_overspent == D("0") and october.overspent_count == 0

    async def test_a_repayment_larger_than_the_category_ever_charged(self, db_session):
        """The reimbursement case: Groceries spent its money in cash, and 50
        arrives on the card filed to it. Nothing was riding there, so the card
        ends holding 50 of this envelope's money — a negative reserve, which is
        a real position and not a refusal."""
        services, budget, checking, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, checking, "-100.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "50.00", date(2026, 8, 9), category=groceries
        )
        await db_session.flush()

        august = await _summary(services, budget, AUG)
        card = august.cards[0]
        assert (card.balance, card.set_aside) == (D("50.00"), D("-50.00"))
        assert card.reserve_discrepancy == D("0")
        row = next(b for b in august.category_balances if b.category_id == groceries.id)
        assert row.available == D("50.00")
        # The two cancel in the envelope term, so the figure does not move.
        assert august.to_be_assigned == D("900.00")

    async def test_a_refund_before_its_purchase_is_absorbed_by_the_purchase(self, db_session):
        """July's refund has no reservation behind it yet; August's purchase
        absorbs the negative reserve it left. The old walk wrote the refund off
        permanently and left the reserve standing against a settled card."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "100.00", date(2026, 7, 9), category=groceries
        )
        await create_budget_assignment(db_session, budget, groceries, AUG, "100.00")
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 8, 9), category=groceries
        )
        await db_session.flush()

        august = await _summary(services, budget, AUG)
        card = august.cards[0]
        assert (card.balance, card.set_aside, card.uncovered) == (D("0.00"), D("0.00"), D("0"))
        assert card.reserve_discrepancy == D("0")

    @pytest.mark.parametrize(
        "name,rows,assignment",
        [
            ("wholly ridden, repaid", [("-100.00", 7), ("100.00", 8)], None),
            ("funded, refunded", [("-100.00", 7), ("100.00", 8)], "100.00"),
            ("partly ridden, refunded", [("-100.00", 7), ("100.00", 8)], "60.00"),
            ("refund before purchase", [("100.00", 7), ("-100.00", 8)], None),
            ("repayment beyond exposure", [("50.00", 8)], None),
        ],
    )
    async def test_ready_to_assign_is_unchanged_by_any_card_inflow(
        self, db_session, name, rows, assignment
    ):
        """The identity, over every shape an inflow can take. A card inflow
        moves no cash: whatever it does to the envelope, the card's reserve
        does the opposite, to the cent.

        This is the pin that would have caught the counterweight. It kept Ready
        to Assign exact too — which is precisely why nothing noticed that it was
        booking the whole discrepancy as an envelope overspend."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        if assignment:
            await create_budget_assignment(db_session, budget, groceries, JUL, assignment)
        await db_session.flush()
        before = (await _summary(services, budget, AUG)).to_be_assigned
        for amount, month in rows:
            await create_transaction(
                db_session, budget, visa, amount, date(2026, month, 9), category=groceries
            )
        await db_session.flush()

        after = await _summary(services, budget, AUG)
        assert after.to_be_assigned == before, name
        assert all(c.reserve_discrepancy == D("0") for c in after.cards), name

    async def test_a_correction_never_creates_red_or_a_cover_offer(self, db_session):
        """A repayment is bounded by the inflow that caused it, so at worst it
        returns the month to what it would have been with no refund at all. The
        old counterweight could manufacture a shortfall no assignment could fix
        — and then offer Cover Overspent as the remedy for it."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "100.00", date(2026, 8, 9), category=groceries
        )
        await db_session.flush()

        august = await _summary(services, budget, AUG)
        assert august.overspent_count == 0
        assert august.total_overspent_cash == D("0")
        preview = await services.budgets.cover_overspent_preview(budget.id, AUG)
        assert preview.items == []

    async def test_spending_after_a_correction_does_not_double_count(self, db_session):
        """Why the correction reduces `available` rather than adding a term to
        Ready to Assign.

        July rides 100; August's repayment discharges it, and the envelope ends
        at 0 because no cash arrived. Spend 100 in cash in August and Ready to
        Assign must fall by exactly 100.

        The rejected reading — leave `available` at 100 and add a compensating
        term to the figure — keeps Ready to Assign right until the money is
        spent, and then charges only what the envelope had, so the same 100
        pays for two things. This is the case that decided it.
        """
        services, budget, checking, visa, _, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "100.00", date(2026, 8, 9), category=groceries
        )
        await db_session.flush()

        before = await _summary(services, budget, AUG)
        row_before = next(b for b in before.category_balances if b.category_id == groceries.id)
        assert row_before.available == D("0.00")

        await create_transaction(
            db_session, budget, checking, "-100.00", date(2026, 8, 20), category=groceries
        )
        await db_session.flush()

        after = await _summary(services, budget, AUG)
        row_after = next(b for b in after.category_balances if b.category_id == groceries.id)
        # The envelope had nothing, so the spend is a real shortfall. In its own
        # month that red does not charge the figure yet — the envelope's fall
        # cancels the cash outflow, which is IGAB's ordinary rule.
        assert row_after.available == D("-100.00")
        assert after.to_be_assigned == before.to_be_assigned

        # September is where it lands: the shortfall is written off, and Ready
        # to Assign settles at the cash that is actually left.
        september = await _summary(services, budget, SEP)
        assert september.to_be_assigned == D("900.00")
        assert next(
            b for b in september.category_balances if b.category_id == groceries.id
        ).available == D("0.00")
        # Under the rejected reading the envelope would still have held 100 here
        # — the repayment having been left in it and offset by a term on the
        # figure — so the spend would have been covered, nothing written off,
        # and Ready to Assign would read 1000 against 900 of cash.

    async def test_activity_differs_from_the_register_by_exactly_the_repaid_amount(
        self, db_session
    ):
        """A stated divergence, pinned rather than rediscovered: the row's
        activity is the register's sum minus what the inflow gave back to the
        card instead of to this envelope."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "30.00", date(2026, 8, 9), category=groceries
        )
        await db_session.flush()

        row = next(
            b
            for b in (await _summary(services, budget, AUG)).category_balances
            if b.category_id == groceries.id
        )
        register_sum = D("30.00")
        assert row.repaid_uncovered_debt == D("30.00")
        assert row.activity == register_sum - row.repaid_uncovered_debt == D("0.00")


class TestTheThreeTermsPartitionCardInflows:
    """Every inflow on a card lands in exactly one of the three terms the
    reserve identity is built from: a payment from the budget's cash, a
    category's own money coming back, or a credit the budget has no claim on.

    "Exactly one" is the whole content. Both ways of getting it wrong are
    silent — a row in no term reads as drift on an ordinary history, a row in
    two widens the bounds by its own size and hides real drift behind it — and
    neither moves a figure the user can see.
    """

    async def test_a_card_paid_from_an_off_budget_account_is_not_drift(self, db_session):
        """Somebody outside the budget pays the card off.

        The debt goes; the reserve behind it does not, because no envelope
        gave anything back — over-reserved by exactly the payment, which is
        true and is the user's cue to move that money somewhere. It counted
        as a *card payment* only when the counterpart was cash, and as an
        *unbudgeted credit* only when the row was not a transfer, so this
        landed in neither and the check called the whole reserve unexplained.
        """
        services, budget, _, visa, _, groceries = await _setup(db_session)
        partner = await create_account(db_session, budget, "Outside", on_budget=False)
        await create_budget_assignment(db_session, budget, groceries, JUL, "150.00")
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
        from igab.services.transaction_service import TransactionCreate

        await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=partner.id,
                date=date(2026, 8, 25),
                amount=D("-150.00"),
                transfer_account_id=visa.id,
            ),
        )
        await db_session.flush()

        card = (await _summary(services, budget, AUG)).cards[0]
        assert card.balance == D("0.00")
        assert card.set_aside == D("150.00")
        assert card.reserve_discrepancy == D("0")
        await assert_card_reserve_identity(db_session, budget.id)

    async def test_a_split_refund_on_a_card_is_counted_once(self, db_session):
        """A refund arriving as a split, its legs filed to real envelopes.

        Splitting forces the parent's category to NULL, so measured on the
        parent the refund looked like money nobody claimed — while its legs
        were simultaneously releasing their envelopes' reservations. The same
        120 in two terms, widening the bounds by 120 and hiding real drift of
        that size from the check that exists to find it.

        Also the guard on the widened predicate: legs filed to real envelopes
        are SPENDABLE, so negating that must still leave them out.
        """
        services, budget, _, visa, _, groceries = await _setup(db_session)
        dining = await create_category(
            db_session, budget, await create_category_group(db_session, budget, "Fun"), "Dining"
        )
        await create_budget_assignment(db_session, budget, groceries, JUL, "200.00")
        await create_transaction(
            db_session, budget, visa, "-200.00", date(2026, 7, 9), category=groceries
        )
        parent = await create_transaction(
            db_session, budget, visa, "120.00", date(2026, 8, 9), is_split=True
        )
        for amount, category in ((D("100.00"), groceries), (D("20.00"), dining)):
            await create_transaction(
                db_session,
                budget,
                visa,
                amount,
                date(2026, 8, 9),
                category=category,
                parent_transaction_id=parent.id,
            )
        await db_session.flush()

        credits = await TransactionRepository(db_session).sum_unclaimed_card_rows(budget.id, SEP)
        assert credits.get(visa.id, {}) == {}
        await assert_card_reserve_identity(db_session, budget.id)

    async def test_an_uncategorized_card_inflow_still_counts(self, db_session):
        """The positive control for the two above: a promotional credit, filed
        nowhere and paid by nobody, is exactly what the term is for."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "-200.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(db_session, budget, visa, "25.00", date(2026, 8, 9))
        await db_session.flush()

        credits = await TransactionRepository(db_session).sum_unclaimed_card_rows(budget.id, SEP)
        assert credits[visa.id] == {AUG: D("25.00")}

    async def test_a_card_credit_filed_as_income_is_an_outside_credit(self, db_session):
        """The Watchman's Arithmetic, finding two. A rewards credit, a rebate,
        a class-action cheque — money a person reasonably calls income rather
        than a refund to an envelope.

        The release path claims rows whose category is SPENDABLE; the
        complement was spelled `category_id IS NULL`. Those are different sets,
        and the difference is exactly this row: a category that exists but is
        not spendable. The card's balance fell by 50 and no term moved, so the
        reserve identity reported 50 of drift — permanently, growing with every
        such row, and invisible to the person using the app.
        """
        services, budget, _, visa, _, groceries = await _setup(db_session)
        income = await _income_category(db_session, budget)
        await create_budget_assignment(db_session, budget, groceries, JUL, "200.00")
        await create_transaction(
            db_session, budget, visa, "-200.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "50.00", date(2026, 8, 9), category=income
        )
        await db_session.flush()

        credits = await TransactionRepository(db_session).sum_unclaimed_card_rows(budget.id, SEP)
        assert credits[visa.id] == {AUG: D("50.00")}
        card = (await _summary(services, budget, AUG)).cards[0]
        assert card.balance == D("-150.00")
        assert card.reserve_discrepancy == D("0")
        await assert_card_reserve_identity(db_session, budget.id)

    async def test_a_credit_filed_to_the_cards_own_envelope_is_an_outside_credit(self, db_session):
        """The other half of the same gap. A card's set-aside envelope is
        maintained by the arithmetic, never by a row filed into it — so a row
        that nonetheless points there (an import, a register that used to offer
        it) releases nothing, and must reach the unbudgeted term rather than no
        term at all."""
        services, budget, _, visa, linked, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "-200.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "30.00", date(2026, 8, 9), category=linked
        )
        await db_session.flush()

        credits = await TransactionRepository(db_session).sum_unclaimed_card_rows(budget.id, SEP)
        assert credits[visa.id] == {AUG: D("30.00")}
        await assert_card_reserve_identity(db_session, budget.id)

    async def test_money_moved_back_out_of_a_card_envelope_is_not_a_violation(self, db_session):
        """The Watchman's Arithmetic, finding one, through the whole service.

        July funds 100 of groceries on the card and reserves it. August moves
        that 100 back out of the card's envelope to cover something else —
        ordinary reallocation — leaving the reserve at zero against 100 still
        owed. Nothing is over-reserved, so bound T1 has nothing to account for;
        before the allowances were floored it read `0 - (-100)` and failed the
        integrity page with a four-figure alarm on a card whose arithmetic was
        entirely consistent.
        """
        services, budget, _, visa, linked, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 9), category=groceries
        )
        await create_budget_assignment(db_session, budget, linked, AUG, "-100.00")
        await db_session.flush()

        card = (await _summary(services, budget, AUG)).cards[0]
        assert (card.balance, card.set_aside) == (D("-100.00"), D("0.00"))
        assert card.reserve_discrepancy == D("0")
        await assert_card_reserve_identity(db_session, budget.id)


class TestAnAssignmentRetiresRidingDebt:
    """ "Two Ledgers, One Debt", end to end through the service.

    In YNAB, credit overspending debits the Credit Card Payments category and
    the assignment covering it credits the same category — one ledger, net
    zero. Here the debt deliberately rides on the card, outside the reserve;
    the assignment covering it used to land inside the reserve and nothing
    ever reconciled the two, so on a card always paid in full the reserve
    converged on what the card owed plus every dollar ever assigned to it.

    Nothing in this suite exercised that before: the fixtures never combined a
    card-payment assignment with riding debt, so `assert_card_reserve_identity`
    passed either way.
    """

    async def test_a_refund_after_a_covering_assignment_returns_money_to_the_envelope(
        self, db_session
    ):
        """The headline. Assigning to the card in August covers July's ride;
        September's refund must then hand the money back to Groceries rather
        than disappearing into a discharge that credits nobody."""
        services, budget, checking, visa, linked, groceries = await _setup(db_session)
        # July: 100 spent on the card with nothing assigned — 100 rides.
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 10), category=groceries
        )
        # August: 100 assigned to the card's own envelope, covering it.
        await create_budget_assignment(db_session, budget, linked, AUG, "100.00")
        # September: the goods go back.
        await create_transaction(
            db_session, budget, visa, "100.00", date(2026, 9, 5), category=groceries
        )
        await db_session.flush()

        summary = await _summary(services, budget, SEP)
        card = next(c for c in summary.cards if c.account_id == visa.id)
        assert card.balance == D("0"), "the card is settled"
        # The assignment was spent covering the debt, so nothing is left
        # reserved against a card that owes nothing.
        assert card.set_aside == D("0")
        assert card.uncovered == D("0")
        # And Groceries got its refund, instead of the walk netting it away.
        groceries_row = next(b for b in summary.category_balances if b.category_id == groceries.id)
        assert groceries_row.available == D("100")
        assert card.reserve_discrepancy == D("0")

    async def test_a_covered_ride_stops_a_refund_becoming_a_cash_write_off(self, db_session):
        """The Ready-to-Assign pin, and why this is not cosmetic.

        A stale ride sends the refund down the `discharged` path, where it is
        netted out of the envelope's activity. If the envelope also spent cash
        that month it ends negative — and a negative month with no card outflow
        left to carry it is written off at the boundary as CASH overspending,
        which Ready to Assign pays for and which never comes back.

        The discharged/released split is otherwise neutral to the envelope
        total, so the boundary floor is the whole mechanism by which the defect
        reached Ready to Assign.
        """
        services, budget, checking, visa, linked, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 10), category=groceries
        )
        await create_budget_assignment(db_session, budget, linked, AUG, "100.00")
        # September: 30 of cash spending, and the 100 refund on the card.
        await create_transaction(
            db_session, budget, checking, "-30.00", date(2026, 9, 3), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "100.00", date(2026, 9, 5), category=groceries
        )
        await db_session.flush()

        sep = await _summary(services, budget, SEP)
        groceries_row = next(b for b in sep.category_balances if b.category_id == groceries.id)
        # 100 back, 30 spent: the envelope is 70 up and nothing is overspent.
        assert groceries_row.available == D("70")
        assert sep.total_overspent == D("0"), "no cash write-off to absorb"

        # October: the boundary has passed. Ready to Assign is unharmed.
        octo = await _summary(services, budget, OCT)
        assert octo.total_overspent == D("0")
        card = next(c for c in octo.cards if c.account_id == visa.id)
        assert card.reserve_discrepancy == D("0")

    async def test_an_assignment_covering_this_months_ride_leaves_the_red_alone(self, db_session):
        """Step 5 runs after the charges, so an assignment made in the month a
        category overspends covers that month's ride. The category still shows
        its red and `uncovered_current` still subtracts it — retracting the
        ride would charge Ready to Assign twice for one shortfall."""
        services, budget, checking, visa, linked, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 10), category=groceries
        )
        await create_budget_assignment(db_session, budget, linked, JUL, "100.00")
        await db_session.flush()

        summary = await _summary(services, budget, JUL)
        card = next(c for c in summary.cards if c.account_id == visa.id)
        assert card.set_aside == D("100")
        assert card.uncovered == D("0"), "the assignment covers what is owed"
        groceries_row = next(b for b in summary.category_balances if b.category_id == groceries.id)
        assert groceries_row.available == D("-100"), "the envelope is still red this month"
        assert card.reserve_discrepancy == D("0")

    async def test_an_assignment_parked_on_a_settled_card_is_named_as_over_reserve(
        self, db_session
    ):
        """The defect's own shape, now caught rather than excused.

        Charge, pay in full, assign — and the assignment sits on a card that
        owes nothing. T1 used to accept the assignment as the explanation for
        the reserve it caused, so the further the reserve drifted the more
        thoroughly the check was satisfied. It is still a legitimate state to
        be in (pre-funding a card), which is why it is reported rather than
        refused: what changed is that an assignment which has already retired a
        ride no longer explains anything.
        """
        services, budget, checking, visa, linked, groceries = await _setup(db_session)
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 10), category=groceries
        )
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        # Pay the card off from cash — a real transfer, because
        # `CARD_PAYMENT_FROM_CASH` is a transfer leg whose counterpart is cash.
        from igab.services.transaction_service import TransactionCreate

        await db_session.flush()
        await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=date(2026, 8, 1),
                amount=D("-100.00"),
                transfer_account_id=visa.id,
            ),
        )
        await create_budget_assignment(db_session, budget, linked, SEP, "250.00")
        await db_session.flush()

        summary = await _summary(services, budget, SEP)
        card = next(c for c in summary.cards if c.account_id == visa.id)
        # Nothing rode (the spending was funded), so nothing was covered and
        # the assignment still explains the reserve standing on the card.
        assert card.set_aside == D("250")
        assert card.reserve_discrepancy == D("0")


class TestTheFiveLegs:
    """A card's reserve is a running total of five things and the surface used
    to show only the total. Every question this model raised — the refused
    repayment, the unreleased reservation, the assignment that never left —
    was answered by decomposing one number into the flows that produced it,
    and a user could not do that."""

    async def test_the_five_legs_reconstruct_the_set_aside(self, db_session):
        services, budget, checking, visa, linked, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
        )
        await create_budget_assignment(db_session, budget, linked, JUL, "40.00")
        # A partial refund, and a payment.
        await create_transaction(
            db_session, budget, visa, "30.00", date(2026, 8, 4), category=groceries
        )
        from igab.services.transaction_service import TransactionCreate

        await db_session.flush()
        await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=date(2026, 8, 20),
                amount=D("-25.00"),
                transfer_account_id=visa.id,
            ),
        )
        await db_session.flush()

        card = next(c for c in (await _summary(services, budget, AUG)).cards)
        assert (
            card.assigned + card.reserved - card.released - card.residual - card.payments
            == card.set_aside
        ), (
            f"legs do not reconstruct the reserve: assigned={card.assigned} "
            f"reserved={card.reserved} released={card.released} "
            f"residual={card.residual} payments={card.payments} "
            f"set_aside={card.set_aside}"
        )
        # And each leg says something. Note what the decomposition shows that
        # the total cannot: 150 was spent with 100 funded, so 50 rode. July's
        # 40 assignment to the card covered 40 of it, leaving 10 riding — so
        # August's 30 refund discharges that 10 and releases only the other 20.
        # Before assignments entered the walk the ride would still have been
        # 50, the whole 30 would have discharged, and Groceries would have got
        # nothing back.
        assert card.assigned == D("40")
        assert card.reserved == D("100")
        assert card.payments == D("25")
        assert card.released == D("20")
        assert card.residual == D("0")

    async def test_every_card_row_carries_the_legs_over_the_api(self, api_client, db_session):
        """Required, not optional, on the response schema: a path that forgets
        must raise rather than serve a reserve made of zeros."""
        # The budget has to belong to the authenticated client's user, or the
        # route answers 404 before it ever serializes a card.
        budget = await create_budget(db_session, api_client.test_user)
        visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
        await ensure_payment_category(db_session, visa)
        everyday = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, everyday, "Groceries")
        await create_transaction(
            db_session, budget, visa, "-60.00", date(2026, 7, 9), category=groceries
        )
        await db_session.flush()

        resp = await api_client.get(f"/api/v1/{budget.id}/months/2026-07-01")
        assert resp.status_code == 200
        cards = resp.json()["cards"]
        assert cards, "no card row served"
        for card in cards:
            for leg in (
                "assigned",
                "reserved",
                "released",
                "residual",
                "payments",
                "riding",
                # The position, beside `uncovered`. Required on the schema, so
                # a path that forgets one 500s rather than serving a row the
                # surface then reads as all-zeros and calls healthy.
                "over_reserved",
                "short_reserved",
                "card_credit",
                # The viewed month off the card's own ledger.
                "charged_this_month",
                "paid_this_month",
                "debt_change_this_month",
                "pending_this_month",
                "rode_by_month",
            ):
                assert leg in card, f"{leg} missing from the served card row"


class TestTheMonthAndThePosition:
    """What the row needs to explain itself, served and walked end to end.

    Amounts here are invented and rescaled from the budget that raised the
    question — the ratios carry the lesson, the digits are nobody's.
    """

    async def test_a_payment_past_the_reserve_is_not_an_overpayment(self, db_session):
        """The screenshot, walked. A card owing a full balance, a payment
        larger than anything an envelope reserved, and the word "overpaid" on
        the row. `card_credit` — the only state that word is true of — is
        zero."""
        services, budget, checking, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        # A carried balance the budget never funded, plus a funded charge.
        await create_transaction(db_session, budget, visa, "-400.00", date(2026, 7, 1))
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 9), category=groceries
        )
        from igab.services.transaction_service import TransactionCreate

        await db_session.flush()
        before = (await _summary(services, budget, JUL)).cards[0]
        await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=date(2026, 7, 25),
                amount=D("-160.00"),
                transfer_account_id=visa.id,
            ),
        )
        await db_session.flush()
        after = (await _summary(services, budget, JUL)).cards[0]

        assert after.set_aside == D("-60.00")
        assert after.short_reserved == D("60.00")
        # Nothing was overpaid: the card still owes 340.
        assert after.card_credit == D("0")
        assert after.balance == D("-340.00")
        # Uncovered fell by 60, not by the whole 160 — and that is the sharp
        # version of what the row now says. The first 100 of the payment
        # drained the reserve standing behind a FUNDED charge, which was never
        # uncovered; only the 60 beyond it attacked debt nobody was covering.
        # So `short_reserved` is exactly the part of the payment that went to
        # the balance, which is the number the row's note quotes.
        assert before.uncovered - after.uncovered == after.short_reserved == D("60.00")

    async def test_the_month_says_the_debt_shrank(self, db_session):
        """The signal the strip never carried. Charged less than paid, so the
        debt fell — and the balance RISING is what that looks like raw, which
        is why the row phrases it as debt."""
        services, budget, checking, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "500.00")
        await create_transaction(db_session, budget, visa, "-1000.00", date(2026, 6, 20))
        await create_transaction(
            db_session, budget, visa, "-120.00", date(2026, 7, 9), category=groceries
        )
        from igab.services.transaction_service import TransactionCreate

        await db_session.flush()
        await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id,
                date=date(2026, 7, 25),
                amount=D("-300.00"),
                transfer_account_id=visa.id,
            ),
        )
        await db_session.flush()

        card = (await _summary(services, budget, JUL)).cards[0]
        assert card.charged_this_month == D("120.00")
        assert card.paid_this_month == D("300.00")
        assert card.debt_change_this_month == D("180.00")
        # June's charge is outside the window, so the month figures do not see
        # it while the lifetime legs and the balance do.
        assert card.balance == D("-820.00")

    async def test_the_month_excludes_pending_and_says_by_how_much(self, db_session):
        """The register and the panel disagree, on purpose, and the panel says
        so.

        `POSTED` keeps a provisional row out of every money aggregate — the
        month figures AND the balance — while the register lists it the moment
        the bank mentions it. A real card read `charged 2,400` against a
        register its owner counted at `2,700`, with nothing on screen
        accounting for the difference; they reasonably concluded the panel was
        wrong.

        So the divergence is named and bounded: `pending_this_month` is
        exactly what the register shows and these figures do not. It is NOT
        added to them — a pending amount is provisional and often arrives
        changed.
        """
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "500.00")
        await create_transaction(
            db_session, budget, visa, "-120.00", date(2026, 7, 9), category=groceries
        )
        # Two rows the bank has mentioned but not confirmed.
        await create_transaction(
            db_session, budget, visa, "-40.00", date(2026, 7, 28), cleared="pending"
        )
        await create_transaction(
            db_session, budget, visa, "-25.00", date(2026, 7, 29), cleared="pending"
        )
        await db_session.flush()

        card = (await _summary(services, budget, JUL)).cards[0]
        # The posted figures ignore both, and so does the balance beside them:
        # the panel is self-consistent, which is why the gap is invisible.
        assert card.charged_this_month == D("120.00")
        assert card.debt_change_this_month == D("-120.00")
        assert card.balance == D("-120.00")
        # And the gap the register shows is stated rather than left to be found.
        assert card.pending_this_month == D("-65.00")

    async def test_pending_is_zero_when_every_row_has_posted(self, db_session):
        """No note on the common case — the line only earns its place when the
        two screens actually disagree."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "500.00")
        await create_transaction(
            db_session, budget, visa, "-120.00", date(2026, 7, 9), category=groceries
        )
        await db_session.flush()

        card = (await _summary(services, budget, JUL)).cards[0]
        assert card.pending_this_month == D("0")

    async def test_a_pending_credit_is_reported_as_a_credit(self, db_session):
        """Signed, so the surface can say "charges" or "credits" rather than
        guessing. A pending refund is the other direction and reads that way."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "500.00")
        await create_transaction(
            db_session, budget, visa, "-120.00", date(2026, 7, 9), category=groceries
        )
        await create_transaction(
            db_session, budget, visa, "30.00", date(2026, 7, 27), cleared="pending"
        )
        await db_session.flush()

        card = (await _summary(services, budget, JUL)).cards[0]
        assert card.pending_this_month == D("30.00")

    async def test_an_over_reserve_the_discrepancy_check_excuses_still_reports_a_position(
        self, db_session
    ):
        """The correction that reshaped this work. Assignments to a card with
        no ride to retire accumulate for the life of the budget, and T1
        excuses exactly that — so `reserve_discrepancy` is silent on the card
        that has drifted furthest. `over_reserved` is what the row reads."""
        services, budget, _, visa, linked, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "100.00")
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 9), category=groceries
        )
        # Money put on the card ahead of any debt — the roadmap's own advice.
        await create_budget_assignment(db_session, budget, linked, JUL, "400.00")
        await db_session.flush()

        card = (await _summary(services, budget, JUL)).cards[0]
        assert card.reserve_discrepancy == D("0")
        assert card.set_aside == D("500.00")
        assert card.over_reserved == D("400.00")

    async def test_the_month_that_ended_short_is_named(self, db_session):
        """The remedy needs the month: funding an envelope in the month it
        ended short retires the ride, funding it the month after does not."""
        services, budget, _, visa, _, groceries = await _setup(db_session)
        await create_budget_assignment(db_session, budget, groceries, JUL, "40.00")
        await create_transaction(
            db_session, budget, visa, "-100.00", date(2026, 7, 28), category=groceries
        )
        await db_session.flush()

        card = (await _summary(services, budget, AUG)).cards[0]
        assert card.rode_by_month == [(JUL, D("60.00"))]
        assert card.riding == D("60.00")


async def test_the_payment_endpoint_shape_spends_the_reserve(api_client, db_session):
    """The exact POST the card page's "Make a payment" modal sends: from the
    CASH side, amount −|payment|, transfer_account_id = the card — the server
    writes −|amount| on account_id and +|amount| on the partner, so the supply
    account must be the source. The card leg must satisfy
    CARD_PAYMENT_FROM_CASH, the only shape that spends the set-aside; a
    payment typed any other way lowers the balance while Ready to pay stands
    still."""
    from igab.db.models import Transaction
    from igab.repositories.txn_filters import CARD_PAYMENT_FROM_CASH

    services = make_services(db_session)
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
    linked = await ensure_payment_category(db_session, visa)
    assert linked is not None
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=inflow
    )
    await create_budget_assignment(db_session, budget, groceries, JUL, "150.00")
    await create_transaction(
        db_session, budget, visa, "-150.00", date(2026, 7, 9), category=groceries
    )
    await db_session.flush()

    resp = await api_client.post(
        f"/api/v1/{budget.id}/transactions",
        json={
            "account_id": str(checking.id),
            "date": "2026-07-25",
            "amount": "-150.00",
            "transfer_account_id": str(visa.id),
            "cleared": "uncleared",
            "approved": True,
        },
    )
    assert resp.status_code == 201, resp.text

    # The card leg is a payment in the credit model's own terms.
    card_leg = (
        (
            await db_session.execute(
                select(Transaction).where(
                    Transaction.account_id == visa.id,
                    Transaction.amount > 0,
                    CARD_PAYMENT_FROM_CASH,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(card_leg) == 1
    assert card_leg[0].amount == D("150.00")

    # And it spent the reserve: funded swipe reserved 150, the payment
    # drained it, and the figure (to-be-assigned) never moved.
    s2 = await _summary(services, budget, JUL)
    assert s2.to_be_assigned == D("850.00")
    card = s2.cards[0]
    assert (card.balance, card.set_aside, card.uncovered) == (D("0.00"), D("0.00"), D("0"))
    assert card.payments == D("150.00")
