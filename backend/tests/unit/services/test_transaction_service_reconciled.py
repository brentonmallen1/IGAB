"""
Tests for TransactionService edit/delete invariants around reconciled state.

Core invariants:
  - A reconciled transaction's MONEY cannot change: amount, date, cleared,
    account (domain.reconciliation.RECONCILED_LOCKED_FIELDS)
  - Its BOOKKEEPING can: category, payee, memo, approval
  - Reconciled transactions CANNOT be deleted (raises InvariantViolation)
  - All other cleared states (pending, uncleared, cleared) CAN be edited and deleted

Once a transaction has been verified against a bank statement, what the
statement vouched for must not move. Fixing a wrong category or memo was
never part of that verification, and a blanket "cannot edit" used to force
the user to unreconcile (and re-reconcile) just to file a row correctly.

The reconciliation flow:
  1. finish() bulk-updates all 'cleared' transactions → 'reconciled'
  2. From that point on, update() refuses changes to the locked fields and
     delete() refuses the row
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.services.transaction_service import TransactionService, TransactionUpdate

BUDGET_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def D(s: str) -> Decimal:
    return Decimal(s)


@dataclass
class MockTransaction:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    budget_id: uuid.UUID = BUDGET_ID
    account_id: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
    amount: Decimal = Decimal("-10.00")
    date: date = date(2026, 7, 10)
    cleared: str = "uncleared"
    transfer_id: uuid.UUID | None = None
    parent_transaction_id: uuid.UUID | None = None
    is_split: bool = False
    is_deleted: bool = False


def make_service(txn: MockTransaction) -> TransactionService:
    """TransactionService with a minimal transaction repo mock for update/delete testing."""
    txn_repo = MagicMock()
    txn_repo.refresh = AsyncMock()
    txn_repo.get_or_raise = AsyncMock(return_value=txn)
    txn_repo.update = AsyncMock(return_value=txn)
    txn_repo.soft_delete = AsyncMock()
    txn_repo.get_splits = AsyncMock(return_value=[])

    async def _get(txn_id: uuid.UUID) -> MockTransaction:
        # Transfer-partner lookups get a plain editable partner with that id
        partner = MockTransaction(cleared="uncleared")
        partner.id = txn_id
        return partner

    txn_repo.get = AsyncMock(side_effect=_get)

    # The category rule loads the row's account; an on-budget one keeps these
    # tests about reconciliation, not about the rule.
    account_repo = MagicMock()
    account_repo.get_or_raise = AsyncMock(return_value=MagicMock(on_budget=True))
    return TransactionService(
        session=AsyncMock(),
        transaction_repo=txn_repo,
        account_repo=account_repo,
        category_repo=MagicMock(),
        payee_repo=MagicMock(),
    )


class TestUpdateReconciled:
    """update() refuses to move a reconciled transaction's money and nothing else."""

    async def test_edit_reconciled_amount_blocked(self):
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        with pytest.raises(InvariantViolation, match="reconciled — unlock it to change amount"):
            await svc.update(BUDGET_ID, txn.id, TransactionUpdate(amount=D("999.00")))

    async def test_edit_reconciled_blocked_before_any_repo_write(self):
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        with pytest.raises(InvariantViolation):
            await svc.update(BUDGET_ID, txn.id, TransactionUpdate(amount=D("100.00")))
        svc.transaction_repo.update.assert_not_called()

    async def test_edit_reconciled_date_blocked(self):
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        with pytest.raises(InvariantViolation, match="date"):
            await svc.update(BUDGET_ID, txn.id, TransactionUpdate(date=date(2025, 1, 1)))

    async def test_attempt_to_change_cleared_status_from_reconciled_blocked(self):
        """Cannot change cleared from 'reconciled' to anything else."""
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        with pytest.raises(InvariantViolation, match="cleared"):
            await svc.update(BUDGET_ID, txn.id, TransactionUpdate(cleared="cleared"))

    async def test_edit_reconciled_memo_allowed(self):
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        await svc.update(BUDGET_ID, txn.id, TransactionUpdate(memo="changed"))
        svc.transaction_repo.update.assert_called_once_with(txn.id, memo="changed")

    async def test_edit_reconciled_category_allowed(self, monkeypatch):
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        # The budget-ownership lookup needs a real session; it is not what is
        # under test here.
        monkeypatch.setattr("igab.services.transaction_service.require_in_budget", AsyncMock())
        cat_id = uuid.uuid4()
        await svc.update(BUDGET_ID, txn.id, TransactionUpdate(category_id=cat_id))
        svc.transaction_repo.update.assert_called_once_with(txn.id, category_id=cat_id)

    async def test_edit_reconciled_payee_allowed(self):
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        await svc.update(BUDGET_ID, txn.id, TransactionUpdate(payee_id=None))
        svc.transaction_repo.update.assert_called_once_with(txn.id, payee_id=None)

    async def test_edit_reconciled_approved_allowed(self):
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        await svc.update(BUDGET_ID, txn.id, TransactionUpdate(approved=True))
        svc.transaction_repo.update.assert_called_once_with(txn.id, approved=True)

    async def test_edit_reconciled_with_unchanged_amount_and_date_is_allowed(self):
        """The editor sends every field it shows; an unchanged amount beside a
        new memo is not an attempt to change the amount — and it must not be
        written either, or it would trip the transfer and split rules."""
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        await svc.update(
            BUDGET_ID,
            txn.id,
            TransactionUpdate(amount=D("-10.0000"), date=date(2026, 7, 10), memo="filed"),
        )
        svc.transaction_repo.update.assert_called_once_with(txn.id, memo="filed")


class TestUpdateNonReconciled:
    """update() must succeed for pending, uncleared, and cleared transactions."""

    async def test_edit_uncleared_succeeds(self):
        txn = MockTransaction(cleared="uncleared")
        svc = make_service(txn)
        await svc.update(BUDGET_ID, txn.id, TransactionUpdate(memo="updated"))
        svc.transaction_repo.update.assert_called_once()

    async def test_edit_cleared_succeeds(self):
        txn = MockTransaction(cleared="cleared")
        svc = make_service(txn)
        await svc.update(BUDGET_ID, txn.id, TransactionUpdate(memo="updated"))
        svc.transaction_repo.update.assert_called_once()

    async def test_edit_pending_succeeds(self):
        txn = MockTransaction(cleared="pending")
        svc = make_service(txn)
        await svc.update(BUDGET_ID, txn.id, TransactionUpdate(memo="updated"))
        svc.transaction_repo.update.assert_called_once()

    async def test_edit_uncleared_amount_succeeds(self):
        txn = MockTransaction(cleared="uncleared")
        svc = make_service(txn)
        await svc.update(BUDGET_ID, txn.id, TransactionUpdate(amount=D("200.00")))
        kwargs = svc.transaction_repo.update.call_args
        assert kwargs is not None

    async def test_edit_cleared_to_reconciled_directly_is_blocked(self):
        """
        'reconciled' is granted only by the reconciliation finish flow and
        'pending' belongs to bank sync — neither may be set via update().
        """
        txn = MockTransaction(cleared="cleared")
        svc = make_service(txn)
        for value in ("reconciled", "pending"):
            with pytest.raises(InvariantViolation):
                await svc.update(BUDGET_ID, txn.id, TransactionUpdate(cleared=value))
        svc.transaction_repo.update.assert_not_called()


class TestDeleteReconciled:
    """delete() must raise InvariantViolation for reconciled transactions."""

    async def test_delete_reconciled_raises(self):
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        with pytest.raises(InvariantViolation, match="Cannot delete a reconciled transaction"):
            await svc.delete(BUDGET_ID, txn.id)

    async def test_delete_reconciled_does_not_call_soft_delete(self):
        """No soft_delete call should happen when blocked."""
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        with pytest.raises(InvariantViolation):
            await svc.delete(BUDGET_ID, txn.id)
        svc.transaction_repo.soft_delete.assert_not_called()

    async def test_delete_reconciled_transfer_source_raises(self):
        """Reconciled transfer transactions are also protected from deletion."""
        txn = MockTransaction(cleared="reconciled", transfer_id=uuid.uuid4())
        svc = make_service(txn)
        with pytest.raises(InvariantViolation):
            await svc.delete(BUDGET_ID, txn.id)

    async def test_delete_reconciled_no_splits_deleted(self):
        """When blocked, split children are also not deleted."""
        txn = MockTransaction(cleared="reconciled")
        svc = make_service(txn)
        with pytest.raises(InvariantViolation):
            await svc.delete(BUDGET_ID, txn.id)
        svc.transaction_repo.get_splits.assert_not_called()
        svc.transaction_repo.soft_delete.assert_not_called()


class TestDeleteNonReconciled:
    """delete() must succeed for pending, uncleared, and cleared transactions."""

    async def test_delete_uncleared_succeeds(self):
        txn = MockTransaction(cleared="uncleared")
        svc = make_service(txn)
        await svc.delete(BUDGET_ID, txn.id)
        svc.transaction_repo.soft_delete.assert_called_with(txn.id)

    async def test_delete_cleared_succeeds(self):
        txn = MockTransaction(cleared="cleared")
        svc = make_service(txn)
        await svc.delete(BUDGET_ID, txn.id)
        svc.transaction_repo.soft_delete.assert_called_with(txn.id)

    async def test_delete_pending_succeeds(self):
        txn = MockTransaction(cleared="pending")
        svc = make_service(txn)
        await svc.delete(BUDGET_ID, txn.id)
        svc.transaction_repo.soft_delete.assert_called_with(txn.id)

    async def test_delete_uncleared_with_splits_deletes_children(self):
        """Deleting a transaction with splits also soft-deletes each child."""
        parent = MockTransaction(cleared="uncleared")
        child1 = MockTransaction(cleared="uncleared", parent_transaction_id=parent.id)
        child2 = MockTransaction(cleared="uncleared", parent_transaction_id=parent.id)

        txn_repo = MagicMock()
        txn_repo.refresh = AsyncMock()
        txn_repo.get_or_raise = AsyncMock(return_value=parent)
        txn_repo.soft_delete = AsyncMock()
        txn_repo.get_splits = AsyncMock(return_value=[child1, child2])

        svc = TransactionService(
            session=AsyncMock(),
            transaction_repo=txn_repo,
            account_repo=MagicMock(),
            category_repo=MagicMock(),
            payee_repo=MagicMock(),
        )
        await svc.delete(BUDGET_ID, parent.id)

        # Should have deleted: child1, child2, parent = 3 soft_delete calls
        assert txn_repo.soft_delete.call_count == 3

    async def test_delete_transfer_also_deletes_paired(self):
        """Deleting a transfer deletes the paired transaction too."""
        paired_id = uuid.uuid4()
        txn = MockTransaction(cleared="uncleared", transfer_id=paired_id)
        svc = make_service(txn)

        await svc.delete(BUDGET_ID, txn.id)

        # soft_delete called for partner + original
        assert svc.transaction_repo.soft_delete.call_count == 2
        calls = [call.args[0] for call in svc.transaction_repo.soft_delete.call_args_list]
        assert paired_id in calls
        assert txn.id in calls


class TestBudgetIdValidation:
    """Transactions from a different budget are rejected before the reconciled check."""

    async def test_update_wrong_budget_raises(self):
        other_budget = uuid.UUID("00000000-0000-0000-0000-000000000099")
        txn = MockTransaction(budget_id=other_budget, cleared="uncleared")
        svc = make_service(txn)
        with pytest.raises(InvariantViolation, match="does not belong"):
            await svc.update(BUDGET_ID, txn.id, TransactionUpdate(memo="x"))

    async def test_delete_wrong_budget_raises(self):
        other_budget = uuid.UUID("00000000-0000-0000-0000-000000000099")
        txn = MockTransaction(budget_id=other_budget, cleared="uncleared")
        svc = make_service(txn)
        with pytest.raises(InvariantViolation, match="does not belong"):
            await svc.delete(BUDGET_ID, txn.id)
