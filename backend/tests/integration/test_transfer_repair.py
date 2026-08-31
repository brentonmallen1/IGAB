"""Repairing transfers by hand: PATCH transfer_account_id.

The editor's "Transfer to account" control sent this field for months and the
server dropped it on the floor — `TransactionUpdate` had no such field and
Pydantic ignores extras — so the only repair path in the UI was a no-op. That
mattered most exactly when the importer had left legs unpaired.

The rules under test, all of which move money if they are wrong:
  - the pair stays zero-sum, and no path silently writes a duplicate leg;
  - ambiguity is refused, never guessed;
  - breaking a link keeps both rows (money is never deleted to tidy a link);
  - a reconciled far leg is never moved out from under a reconciliation;
  - a categorized transfer stays legal (on-budget side of an on↔off pair).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import ChangeLog
from igab.domain.exceptions import InvariantViolation
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.transaction_service import TransactionUpdate as SvcTxnUpdate
from igab.services.undo_service import UndoService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date(2026, 8, 20)


async def _setup(db_session, *, target_on_budget=True):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    savings = await create_account(db_session, budget, "Savings", on_budget=target_on_budget)
    return budget, checking, savings


async def _transfer_payee(db_session, budget, account):
    return await PayeeRepository(db_session).find_or_create_transfer(
        budget.id, account.id, account.name
    )


async def _balance(db_session, account) -> Decimal:
    """Sum of every live row in an account — the number the user sees."""
    from sqlalchemy import func, select

    from igab.db.models import Transaction

    total = (
        await db_session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == account.id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.parent_transaction_id.is_(None),
            )
        )
    ).scalar_one()
    return Decimal(str(total))


class TestConvert:
    async def test_links_the_one_obvious_far_leg(self, db_session):
        """The import's leftovers: two legs that describe each other and were
        never linked. Linking must move no money at all."""
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        far = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, payee=to_checking
        )
        before = (await _balance(db_session, checking), await _balance(db_session, savings))

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id, near.id, SvcTxnUpdate(transfer_account_id=savings.id)
        )

        assert updated.transfer_id == far.id
        db_session.expunge_all()
        repo = TransactionRepository(db_session)
        assert (await repo.get_or_raise(far.id)).transfer_id == near.id
        assert (await _balance(db_session, checking), await _balance(db_session, savings)) == before

    async def test_writes_the_far_leg_when_there_is_none(self, db_session):
        """A skipped account at import: the far side never existed, so the
        money is genuinely missing from that account until it is written."""
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id, near.id, SvcTxnUpdate(transfer_account_id=savings.id)
        )

        assert updated.transfer_id is not None
        partner = await TransactionRepository(db_session).get_or_raise(updated.transfer_id)
        assert partner.account_id == savings.id
        assert partner.amount == -near.amount, "the pair is zero-sum"
        assert partner.date == near.date
        assert partner.cleared == "uncleared", "nothing has confirmed it at the bank"
        assert await _balance(db_session, savings) == Decimal("500.00")

    async def test_refuses_to_guess_between_candidates(self, db_session):
        """Two rows could be the far leg. Picking one silently would link the
        wrong money; creating a third would double-count it."""
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        for _ in range(2):
            await create_transaction(
                db_session, budget, savings, "500.00", TODAY, payee=to_checking
            )

        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="choose which one"):
            await services.transactions.update(
                budget.id, near.id, SvcTxnUpdate(transfer_account_id=savings.id)
            )

    async def test_refuses_to_create_alongside_a_plain_lookalike(self, db_session):
        """A bank-imported far leg has an ordinary payee, so nothing points
        back here — but creating a second row for the same movement is how an
        account silently ends up twice the money."""
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        await create_transaction(db_session, budget, savings, "500.00", TODAY, memo="Online xfer")

        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="choose one"):
            await services.transactions.update(
                budget.id, near.id, SvcTxnUpdate(transfer_account_id=savings.id)
            )

    async def test_explicit_pick_links_that_row(self, db_session):
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        wrong = await create_transaction(db_session, budget, savings, "500.00", TODAY)
        right = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, memo="this one"
        )

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id,
            near.id,
            SvcTxnUpdate(transfer_account_id=savings.id, transfer_partner_transaction_id=right.id),
        )
        assert updated.transfer_id == right.id
        repo = TransactionRepository(db_session)
        assert (await repo.get_or_raise(wrong.id)).transfer_id is None

    async def test_create_anyway_is_possible_but_deliberate(self, db_session):
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        await create_transaction(db_session, budget, savings, "500.00", TODAY)

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id,
            near.id,
            SvcTxnUpdate(transfer_account_id=savings.id, transfer_create_partner=True),
        )
        assert updated.transfer_id is not None
        assert await _balance(db_session, savings) == Decimal("1000.00"), (
            "two rows now, because the user said so"
        )

    async def test_a_pick_with_the_wrong_amount_is_refused(self, db_session):
        budget, checking, savings = await _setup(db_session)
        near = await create_transaction(db_session, budget, checking, "-500.00", TODAY)
        mismatched = await create_transaction(db_session, budget, savings, "400.00", TODAY)

        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="not the opposite"):
            await services.transactions.update(
                budget.id,
                near.id,
                SvcTxnUpdate(
                    transfer_account_id=savings.id,
                    transfer_partner_transaction_id=mismatched.id,
                ),
            )

    async def test_a_pick_already_in_a_transfer_is_refused(self, db_session):
        budget, checking, savings = await _setup(db_session)
        third = await create_account(db_session, budget, "Third")
        near = await create_transaction(db_session, budget, checking, "-500.00", TODAY)
        taken = await create_transaction(db_session, budget, savings, "500.00", TODAY)
        other = await create_transaction(db_session, budget, third, "-500.00", TODAY)
        taken.transfer_id = other.id
        other.transfer_id = taken.id
        await db_session.flush()

        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="already part of a transfer"):
            await services.transactions.update(
                budget.id,
                near.id,
                SvcTxnUpdate(
                    transfer_account_id=savings.id, transfer_partner_transaction_id=taken.id
                ),
            )

    async def test_same_account_is_refused(self, db_session):
        budget, checking, _ = await _setup(db_session)
        txn = await create_transaction(db_session, budget, checking, "-500.00", TODAY)
        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="two different accounts"):
            await services.transactions.update(
                budget.id, txn.id, SvcTxnUpdate(transfer_account_id=checking.id)
            )

    async def test_another_budgets_account_is_refused(self, db_session):
        budget, checking, _ = await _setup(db_session)
        other_user = await create_user(db_session)
        other_budget = await create_budget(db_session, other_user)
        theirs = await create_account(db_session, other_budget, "Theirs")
        txn = await create_transaction(db_session, budget, checking, "-500.00", TODAY)

        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="does not belong to this budget"):
            await services.transactions.update(
                budget.id, txn.id, SvcTxnUpdate(transfer_account_id=theirs.id)
            )

    async def test_a_candidate_a_day_off_is_not_auto_linked(self, db_session):
        """Auto-linking is exact by design; near-misses go through the picker
        so the user confirms the two rows really are one movement."""
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        far = await create_transaction(
            db_session,
            budget,
            savings,
            "500.00",
            TODAY + timedelta(days=1),
            payee=to_checking,
        )

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id, near.id, SvcTxnUpdate(transfer_account_id=savings.id)
        )
        assert updated.transfer_id is not None
        assert updated.transfer_id != far.id, "a new leg, not a guess at the day-off row"


class TestRetarget:
    async def test_moves_the_partner_and_renames_both_payees(self, db_session):
        budget, checking, savings = await _setup(db_session)
        vacation = await create_account(db_session, budget, "Vacation Fund")
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        far = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, payee=to_checking, transfer_id=near.id
        )
        near.transfer_id = far.id
        await db_session.flush()

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id, near.id, SvcTxnUpdate(transfer_account_id=vacation.id)
        )

        repo = TransactionRepository(db_session)
        moved = await repo.get_or_raise(far.id)
        assert moved.account_id == vacation.id
        assert updated.counterpart_account_id == vacation.id
        assert await _balance(db_session, savings) == Decimal("0")
        assert await _balance(db_session, vacation) == Decimal("500.00")
        payees = PayeeRepository(db_session)
        assert (await payees.get_or_raise(updated.payee_id)).name == "Transfer : Vacation Fund"
        assert (await payees.get_or_raise(moved.payee_id)).name == "Transfer : Checking"

    async def test_refuses_when_the_far_leg_is_reconciled(self, db_session):
        """Moving a reconciled row to another account would invalidate a
        reconciliation the user already signed off."""
        budget, checking, savings = await _setup(db_session)
        vacation = await create_account(db_session, budget, "Vacation Fund")
        near = await create_transaction(db_session, budget, checking, "-500.00", TODAY)
        far = await create_transaction(
            db_session,
            budget,
            savings,
            "500.00",
            TODAY,
            cleared="reconciled",
            transfer_id=near.id,
        )
        near.transfer_id = far.id
        await db_session.flush()

        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="reconciled"):
            await services.transactions.update(
                budget.id, near.id, SvcTxnUpdate(transfer_account_id=vacation.id)
            )

    async def test_retargeting_to_where_it_already_points_is_a_no_op(self, db_session):
        budget, checking, savings = await _setup(db_session)
        near = await create_transaction(db_session, budget, checking, "-500.00", TODAY)
        far = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, transfer_id=near.id
        )
        near.transfer_id = far.id
        await db_session.flush()

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id, near.id, SvcTxnUpdate(transfer_account_id=savings.id)
        )
        assert updated.transfer_id == far.id
        assert await _balance(db_session, savings) == Decimal("500.00")


class TestBreak:
    async def test_unlinks_both_and_keeps_the_money(self, db_session):
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        far = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, payee=to_checking, transfer_id=near.id
        )
        near.transfer_id = far.id
        await db_session.flush()

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id, near.id, SvcTxnUpdate(transfer_account_id=None)
        )

        repo = TransactionRepository(db_session)
        assert updated.transfer_id is None
        assert (await repo.get_or_raise(far.id)).transfer_id is None
        assert await _balance(db_session, checking) == Decimal("-500.00")
        assert await _balance(db_session, savings) == Decimal("500.00")
        # Both keep their transfer payees, so `is:unpaired` still finds them
        # and the link can be remade.
        assert updated.counterpart_account_id == savings.id

    async def test_breaking_an_orphan_leg_clears_its_transfer_payee(self, db_session):
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        orphan = await create_transaction(
            db_session, budget, checking, "-25.00", TODAY, payee=to_savings
        )

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id, orphan.id, SvcTxnUpdate(transfer_account_id=None)
        )
        assert updated.payee_id is None
        assert updated.counterpart_account_id is None, "now an ordinary row needing a category"

    async def test_breaking_a_plain_transaction_changes_nothing(self, db_session):
        budget, checking, _ = await _setup(db_session)
        plain = await create_transaction(db_session, budget, checking, "-25.00", TODAY)
        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id, plain.id, SvcTxnUpdate(transfer_account_id=None)
        )
        assert updated.payee_id is None
        assert updated.transfer_id is None


class TestCategoryInvariant:
    async def test_categorized_transfer_to_a_tracked_account_is_allowed(self, db_session):
        """A YNAB spending transfer: mortgage payment out of checking."""
        budget, checking, mortgage = await _setup(db_session, target_on_budget=False)
        group = await create_category_group(db_session, budget, "Bills")
        cat = await create_category(db_session, budget, group, "Mortgage")
        near = await create_transaction(
            db_session, budget, checking, "-2000.00", TODAY, category=cat
        )

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id, near.id, SvcTxnUpdate(transfer_account_id=mortgage.id)
        )
        assert updated.category_id == cat.id
        assert updated.counterpart_account_id == mortgage.id

    async def test_categorized_transfer_between_on_budget_accounts_is_refused(self, db_session):
        """Both legs sit inside the budget, so counting either as spending
        double-counts money that never left."""
        budget, checking, savings = await _setup(db_session)
        group = await create_category_group(db_session, budget, "Bills")
        cat = await create_category(db_session, budget, group, "Groceries")
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, category=cat
        )

        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="on-budget side"):
            await services.transactions.update(
                budget.id, near.id, SvcTxnUpdate(transfer_account_id=savings.id)
            )

    async def test_clearing_the_category_in_the_same_edit_makes_it_legal(self, db_session):
        """The rule judges where the row ENDS UP, not where it started."""
        budget, checking, savings = await _setup(db_session)
        group = await create_category_group(db_session, budget, "Bills")
        cat = await create_category(db_session, budget, group, "Groceries")
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, category=cat
        )

        services = make_services(db_session)
        updated = await services.transactions.update(
            budget.id,
            near.id,
            SvcTxnUpdate(transfer_account_id=savings.id, category_id=None),
        )
        assert updated.category_id is None
        assert updated.counterpart_account_id == savings.id


class TestGuards:
    async def test_a_linked_legs_payee_cannot_be_edited(self, db_session):
        budget, checking, savings = await _setup(db_session)
        near = await create_transaction(db_session, budget, checking, "-500.00", TODAY)
        far = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, transfer_id=near.id
        )
        near.transfer_id = far.id
        await db_session.flush()
        other = await PayeeRepository(db_session).create(budget_id=budget.id, name="Corner Store")

        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="payee is its destination"):
            await services.transactions.update(budget.id, near.id, SvcTxnUpdate(payee_id=other.id))

    async def test_a_split_cannot_become_a_transfer(self, db_session):
        budget, checking, savings = await _setup(db_session)
        parent = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, is_split=True
        )
        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="split"):
            await services.transactions.update(
                budget.id, parent.id, SvcTxnUpdate(transfer_account_id=savings.id)
            )

    async def test_money_and_link_edits_are_kept_apart(self, db_session):
        budget, checking, savings = await _setup(db_session)
        txn = await create_transaction(db_session, budget, checking, "-500.00", TODAY)
        services = make_services(db_session)
        with pytest.raises(InvariantViolation, match="separate edits"):
            await services.transactions.update(
                budget.id,
                txn.id,
                SvcTxnUpdate(transfer_account_id=savings.id, amount=Decimal("-600.00")),
            )


class TestUndo:
    async def test_linking_is_undoable_as_one_step(self, db_session):
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        far = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, payee=to_checking
        )

        services = make_services(db_session)
        await services.transactions.update(
            budget.id, near.id, SvcTxnUpdate(transfer_account_id=savings.id)
        )

        await db_session.flush()
        changes = list(
            (
                await db_session.execute(
                    select(ChangeLog)
                    .where(ChangeLog.budget_id == budget.id, ChangeLog.entity_type == "transaction")
                    .order_by(ChangeLog.seq)
                )
            )
            .scalars()
            .all()
        )
        # Both legs moved, so both were recorded — under ONE batch id, or undo
        # would unlink one side and leave the other pointing at it.
        assert len(changes) == 2
        assert changes[0].batch_id is not None
        assert changes[0].batch_id == changes[1].batch_id

        await UndoService(db_session).undo_batch(budget.id, changes[0].batch_id)

        db_session.expunge_all()
        repo = TransactionRepository(db_session)
        assert (await repo.get_or_raise(near.id)).transfer_id is None
        assert (await repo.get_or_raise(far.id)).transfer_id is None


class TestRepairPass:
    """Repairing history the fixed importer can't reach.

    A budget imported before the pairing fix carries orphan legs in bulk (one
    real export left 1,117). The pass links the unmistakable ones and refuses
    the rest. It writes no money and creates no rows — only `transfer_id` —
    so every balance in the budget must be identical afterwards.
    """

    async def _orphan_pair(self, db_session, budget, checking, savings, amount, on=TODAY):
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        near = await create_transaction(
            db_session, budget, checking, f"-{amount}", on, payee=to_savings
        )
        far = await create_transaction(db_session, budget, savings, amount, on, payee=to_checking)
        return near, far

    async def test_links_the_unmistakable_pairs_and_moves_no_money(self, db_session):
        budget, checking, savings = await _setup(db_session)
        a_near, a_far = await self._orphan_pair(db_session, budget, checking, savings, "500.00")
        b_near, b_far = await self._orphan_pair(db_session, budget, checking, savings, "25.00")
        before = (await _balance(db_session, checking), await _balance(db_session, savings))

        services = make_services(db_session)
        result = await services.transactions.repair_transfers(budget.id)

        assert result == {"linked": 2, "ambiguous": 0, "remaining": 0}
        repo = TransactionRepository(db_session)
        assert (await repo.get_or_raise(a_near.id)).transfer_id == a_far.id
        assert (await repo.get_or_raise(b_far.id)).transfer_id == b_near.id
        assert (await _balance(db_session, checking), await _balance(db_session, savings)) == before

    async def test_running_it_twice_links_nothing_the_second_time(self, db_session):
        budget, checking, savings = await _setup(db_session)
        await self._orphan_pair(db_session, budget, checking, savings, "500.00")

        services = make_services(db_session)
        first = await services.transactions.repair_transfers(budget.id)
        second = await services.transactions.repair_transfers(budget.id)

        assert first["linked"] == 1
        assert second == {"linked": 0, "ambiguous": 0, "remaining": 0}

    async def test_ambiguous_clusters_are_left_for_a_person(self, db_session):
        """Two identical candidates. Guessing would link the wrong money and
        nothing downstream would ever question it."""
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        for _ in range(2):
            await create_transaction(
                db_session, budget, savings, "500.00", TODAY, payee=to_checking
            )

        services = make_services(db_session)
        result = await services.transactions.repair_transfers(budget.id)

        assert result["linked"] == 0
        assert result["ambiguous"] >= 1
        assert (await TransactionRepository(db_session).get_or_raise(near.id)).transfer_id is None

    async def test_ambiguity_is_seen_from_the_crowded_side_or_not_at_all(self, db_session):
        """The same cluster, walked from the other end.

        `list_unpaired_transfer_legs` orders by (date, created_at), and every
        row one import wrote shares both — `func.now()` is the transaction's
        start time — so Postgres may hand back the two savings legs before the
        checking leg they both match. Each of THOSE sees exactly one
        candidate, and the pass used to link an arbitrary half of the pair:
        precisely the guess it exists to refuse. It surfaced as a CI flake
        rather than as a wrong number in a report, which was the lucky
        version.
        """
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings
        )
        for _ in range(2):
            await create_transaction(
                db_session, budget, savings, "500.00", TODAY, payee=to_checking
            )

        services = make_services(db_session)
        original = services.transaction_repo.list_unpaired_transfer_legs

        async def crowded_side_last(budget_id):
            legs = await original(budget_id)
            return sorted(legs, key=lambda leg: 0 if leg.account_id == savings.id else 1)

        services.transaction_repo.list_unpaired_transfer_legs = crowded_side_last
        result = await services.transactions.repair_transfers(budget.id)

        assert result["linked"] == 0, "linked one of two identical candidates"
        assert result["ambiguous"] >= 1
        assert (await TransactionRepository(db_session).get_or_raise(near.id)).transfer_id is None

    async def test_a_leg_with_no_far_side_is_reported_not_invented(self, db_session):
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        await create_transaction(db_session, budget, checking, "-500.00", TODAY, payee=to_savings)
        before = await _balance(db_session, savings)

        services = make_services(db_session)
        result = await services.transactions.repair_transfers(budget.id)

        assert result == {"linked": 0, "ambiguous": 0, "remaining": 1}
        assert await _balance(db_session, savings) == before, "the pass never writes a row"

    async def test_a_day_apart_links_only_within_the_tolerance_asked_for(self, db_session):
        budget, checking, savings = await _setup(db_session)
        await self._orphan_pair(db_session, budget, checking, savings, "500.00")
        # Shift the far leg a day so the exact-date pass cannot claim it.
        far = (
            await TransactionRepository(db_session).find_transfer_candidates(
                account_id=savings.id, amount=Decimal("500.00")
            )
        )[0]
        far.date = TODAY + timedelta(days=1)
        await db_session.flush()

        services = make_services(db_session)
        assert (await services.transactions.repair_transfers(budget.id))["linked"] == 0
        widened = await services.transactions.repair_transfers(budget.id, date_tolerance_days=1)
        assert widened["linked"] == 1

    async def test_a_reconciled_leg_may_still_be_linked(self, db_session):
        """Linking writes only transfer_id — no amount, no cleared state — so
        a reconciliation the user already signed off stays valid."""
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings, cleared="reconciled"
        )
        far = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, payee=to_checking, cleared="reconciled"
        )

        services = make_services(db_session)
        assert (await services.transactions.repair_transfers(budget.id))["linked"] == 1
        repo = TransactionRepository(db_session)
        assert (await repo.get_or_raise(near.id)).transfer_id == far.id
        assert (await repo.get_or_raise(near.id)).cleared == "reconciled"

    async def test_the_whole_pass_undoes_as_one_batch(self, db_session):
        budget, checking, savings = await _setup(db_session)
        near, far = await self._orphan_pair(db_session, budget, checking, savings, "500.00")

        services = make_services(db_session)
        await services.transactions.repair_transfers(budget.id)
        await db_session.flush()

        changes = list(
            (
                await db_session.execute(
                    select(ChangeLog)
                    .where(ChangeLog.budget_id == budget.id, ChangeLog.entity_type == "transaction")
                    .order_by(ChangeLog.seq)
                )
            )
            .scalars()
            .all()
        )
        assert len({c.batch_id for c in changes}) == 1, "one undo, not one per row"
        await UndoService(db_session).undo_batch(budget.id, changes[0].batch_id)

        db_session.expunge_all()
        repo = TransactionRepository(db_session)
        assert (await repo.get_or_raise(near.id)).transfer_id is None
        assert (await repo.get_or_raise(far.id)).transfer_id is None

    async def test_it_does_not_reach_into_another_budget(self, db_session):
        budget, checking, savings = await _setup(db_session)
        await self._orphan_pair(db_session, budget, checking, savings, "500.00")
        other_budget, other_checking, other_savings = await _setup(db_session)
        other_near, _ = await self._orphan_pair(
            db_session, other_budget, other_checking, other_savings, "500.00"
        )

        services = make_services(db_session)
        assert (await services.transactions.repair_transfers(budget.id))["linked"] == 1
        assert (
            await TransactionRepository(db_session).get_or_raise(other_near.id)
        ).transfer_id is None


class TestRepairCategoryLegality:
    """The auto-pass must not create what the manual paths refuse.

    Found in review: `repair_transfers` matched on account, amount and date
    only, so it linked a categorized on-budget↔on-budget pair — the exact
    state `_create_transfer` and `_plan_transfer_edit` reject with a
    user-facing error. The rule now lives once in domain/transfers.py and the
    pass consults it; an illegal pair stays in `remaining`, where the manual
    repair path explains the problem when a person resolves it.
    """

    async def test_repair_refuses_a_categorized_on_on_pair(self, db_session):
        budget, checking, savings = await _setup(db_session)
        to_savings = await _transfer_payee(db_session, budget, savings)
        to_checking = await _transfer_payee(db_session, budget, checking)
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_savings, category=groceries
        )
        far = await create_transaction(
            db_session, budget, savings, "500.00", TODAY, payee=to_checking
        )

        services = make_services(db_session)
        result = await services.transactions.repair_transfers(budget.id)

        # remaining is 1, not 2: UNPAIRED_TRANSFER_LEG counts only
        # *uncategorized* legs, so the categorized side is not in the hygiene
        # list at all — the link attempt comes from the plain side, and the
        # legality check refuses it there.
        assert result == {"linked": 0, "ambiguous": 0, "remaining": 1}
        db_session.expunge_all()
        repo = TransactionRepository(db_session)
        assert (await repo.get_or_raise(near.id)).transfer_id is None
        assert (await repo.get_or_raise(far.id)).transfer_id is None

    async def test_repair_still_links_a_legal_spending_transfer(self, db_session):
        """A category on the on-budget side of an on↔off pair is the YNAB
        spending transfer — exactly what the pass exists to relink. The
        legality check must not be broader than the rule."""
        budget, checking, tracking = await _setup(db_session, target_on_budget=False)
        to_tracking = await _transfer_payee(db_session, budget, tracking)
        to_checking = await _transfer_payee(db_session, budget, checking)
        group = await create_category_group(db_session, budget, "Everyday")
        house = await create_category(db_session, budget, group, "House Fund")
        near = await create_transaction(
            db_session, budget, checking, "-500.00", TODAY, payee=to_tracking, category=house
        )
        far = await create_transaction(
            db_session, budget, tracking, "500.00", TODAY, payee=to_checking
        )

        services = make_services(db_session)
        result = await services.transactions.repair_transfers(budget.id)

        assert result["linked"] == 1
        db_session.expunge_all()
        repo = TransactionRepository(db_session)
        near_after = await repo.get_or_raise(near.id)
        assert near_after.transfer_id == far.id
        assert near_after.category_id == house.id, "linking must not strip the category"

    async def test_repair_refuses_a_category_on_the_off_budget_side(self, db_session):
        budget, checking, tracking = await _setup(db_session, target_on_budget=False)
        to_tracking = await _transfer_payee(db_session, budget, tracking)
        to_checking = await _transfer_payee(db_session, budget, checking)
        group = await create_category_group(db_session, budget, "Everyday")
        house = await create_category(db_session, budget, group, "House Fund")
        await create_transaction(db_session, budget, checking, "-500.00", TODAY, payee=to_tracking)
        far = await create_transaction(
            db_session, budget, tracking, "500.00", TODAY, payee=to_checking, category=house
        )

        services = make_services(db_session)
        result = await services.transactions.repair_transfers(budget.id)

        assert result["linked"] == 0
        db_session.expunge_all()
        assert (await TransactionRepository(db_session).get_or_raise(far.id)).transfer_id is None
