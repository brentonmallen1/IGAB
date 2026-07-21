"""
Comprehensive tests for ReconciliationService.

The reconciliation workflow:
  1. User opens reconciliation panel → calls get_status() to see cleared_balance
  2. User compares to bank statement → if different, creates adjustment via create_adjustment()
  3. User confirms → calls finish() which locks all cleared → reconciled

Key invariant: once reconciled, transactions cannot be edited or deleted.

Cleared state filtering (documented):
  get_status.cleared_balance = sum WHERE cleared IN ('cleared', 'reconciled')
  get_status.uncleared_count = count WHERE cleared == 'uncleared'
  get_status.pending_count  = count WHERE cleared == 'pending'
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from igab.services.reconciliation_service import ReconciliationService

ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
BUDGET_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def D(s: str) -> Decimal:
    return Decimal(s)


@dataclass
class MockAccount:
    id: uuid.UUID = ACCOUNT_ID
    budget_id: uuid.UUID = BUDGET_ID
    name: str = "Checking"


@dataclass
class MockPayee:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "Reconciliation Balance Adjustment"


@dataclass
class MockTransaction:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    account_id: uuid.UUID = ACCOUNT_ID
    amount: Decimal = D("0")
    cleared: str = "cleared"
    memo: str = ""


@dataclass
class MockSnapshot:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    account_id: uuid.UUID = ACCOUNT_ID
    statement_balance: Decimal = D("0")
    cleared_balance: Decimal = D("0")
    adjustment_amount: Decimal = D("0")
    adjustment_transaction_id: uuid.UUID | None = None


def _mock_scalar(value):
    res = MagicMock()
    res.scalar_one.return_value = value
    return res


def make_status_service(cleared_bal, uncleared_count=0, pending_count=0):
    """ReconciliationService whose session returns pre-set get_status values."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[
        _mock_scalar(cleared_bal),
        _mock_scalar(uncleared_count),
        _mock_scalar(pending_count),
    ])
    return ReconciliationService(
        session=session,
        repo=MagicMock(),
        account_repo=MagicMock(),
        payee_repo=MagicMock(),
        transaction_repo=MagicMock(),
    )


def make_adjustment_service(account, payee, created_txn):
    """ReconciliationService wired for testing create_adjustment."""
    account_repo = MagicMock()
    account_repo.get_or_raise = AsyncMock(return_value=account)

    payee_repo = MagicMock()
    payee_repo.find_or_create = AsyncMock(return_value=payee)

    transaction_repo = MagicMock()
    transaction_repo.create = AsyncMock(return_value=created_txn)

    return ReconciliationService(
        session=AsyncMock(),
        repo=MagicMock(),
        account_repo=account_repo,
        payee_repo=payee_repo,
        transaction_repo=transaction_repo,
    )


def make_finish_service(cleared_bal, snapshot, uncleared_count=0, pending_count=0):
    """ReconciliationService wired for testing finish().

    finish() now auto-creates an adjustment when statement != cleared, so the
    adjustment path (account lookup, payee find_or_create, txn create) is
    mocked too, and session.execute serves get_status results first, then
    generic results for any subsequent UPDATE statements.
    """
    session = AsyncMock()
    status_results = iter(
        [
            _mock_scalar(cleared_bal),
            _mock_scalar(uncleared_count),
            _mock_scalar(pending_count),
        ]
    )

    async def _execute(stmt):
        try:
            return next(status_results)
        except StopIteration:
            return MagicMock()

    session.execute = AsyncMock(side_effect=_execute)
    session.flush = AsyncMock()

    repo = MagicMock()
    repo.create = AsyncMock(return_value=snapshot)

    account = MagicMock()
    account.budget_id = BUDGET_ID
    account_repo = MagicMock()
    account_repo.get_or_raise = AsyncMock(return_value=account)

    payee = MagicMock()
    payee_repo = MagicMock()
    payee_repo.find_or_create = AsyncMock(return_value=payee)

    adjustment = MagicMock()
    adjustment.id = uuid.uuid4()
    transaction_repo = MagicMock()
    transaction_repo.create = AsyncMock(return_value=adjustment)

    svc = ReconciliationService(
        session=session,
        repo=repo,
        account_repo=account_repo,
        payee_repo=payee_repo,
        transaction_repo=transaction_repo,
    )
    svc._test_adjustment = adjustment  # type: ignore[attr-defined]
    return svc


class TestGetStatus:
    async def test_empty_account_all_zeros(self):
        svc = make_status_service(D("0"), 0, 0)
        status = await svc.get_status(ACCOUNT_ID)
        assert status["cleared_balance"] == D("0")
        assert status["uncleared_count"] == 0
        assert status["pending_count"] == 0

    async def test_result_has_required_keys(self):
        svc = make_status_service(D("0"), 0, 0)
        status = await svc.get_status(ACCOUNT_ID)
        assert set(status.keys()) == {"cleared_balance", "uncleared_count", "pending_count"}

    async def test_cleared_balance_sum_of_cleared_and_reconciled(self):
        """
        cleared_balance includes both 'cleared' and 'reconciled' transactions.
        $800 cleared + $500 already-reconciled = $1300.
        """
        svc = make_status_service(D("1300.00"))
        status = await svc.get_status(ACCOUNT_ID)
        assert status["cleared_balance"] == D("1300.00")

    async def test_pending_not_in_cleared_balance(self):
        """
        Pending transactions are excluded from cleared_balance.
        Even with 3 pending transactions, cleared_balance reflects only cleared+reconciled.
        """
        svc = make_status_service(D("500.00"), uncleared_count=0, pending_count=3)
        status = await svc.get_status(ACCOUNT_ID)
        assert status["cleared_balance"] == D("500.00")
        assert status["pending_count"] == 3

    async def test_uncleared_not_in_cleared_balance(self):
        """Uncleared transactions are excluded from cleared_balance."""
        svc = make_status_service(D("500.00"), uncleared_count=5)
        status = await svc.get_status(ACCOUNT_ID)
        assert status["cleared_balance"] == D("500.00")
        assert status["uncleared_count"] == 5

    async def test_mixed_states_all_counts_correct(self):
        svc = make_status_service(D("2000.00"), uncleared_count=4, pending_count=2)
        status = await svc.get_status(ACCOUNT_ID)
        assert status["cleared_balance"] == D("2000.00")
        assert status["uncleared_count"] == 4
        assert status["pending_count"] == 2

    async def test_negative_cleared_balance(self):
        """Account can have a negative cleared balance (more cleared debits than credits)."""
        svc = make_status_service(D("-350.00"))
        status = await svc.get_status(ACCOUNT_ID)
        assert status["cleared_balance"] == D("-350.00")

    async def test_decimal_precision_preserved(self):
        svc = make_status_service(D("12345.6789"))
        status = await svc.get_status(ACCOUNT_ID)
        assert status["cleared_balance"] == D("12345.6789")

    async def test_only_pending_transactions(self):
        """Account with only pending transactions has cleared_balance=0."""
        svc = make_status_service(D("0"), uncleared_count=0, pending_count=5)
        status = await svc.get_status(ACCOUNT_ID)
        assert status["cleared_balance"] == D("0")
        assert status["pending_count"] == 5

    async def test_only_uncleared_transactions(self):
        """Account with only uncleared transactions has cleared_balance=0."""
        svc = make_status_service(D("0"), uncleared_count=10)
        status = await svc.get_status(ACCOUNT_ID)
        assert status["cleared_balance"] == D("0")
        assert status["uncleared_count"] == 10


class TestCreateAdjustment:
    async def test_positive_adjustment_amount_correct(self):
        """Positive adjustment: account understated vs bank statement."""
        account = MockAccount()
        payee = MockPayee()
        txn = MockTransaction(amount=D("150.00"), cleared="cleared")
        svc = make_adjustment_service(account, payee, txn)

        await svc.create_adjustment(ACCOUNT_ID, D("150.00"))

        kwargs = svc.transaction_repo.create.call_args.kwargs
        assert kwargs["amount"] == D("150.00")

    async def test_negative_adjustment_amount_correct(self):
        """Negative adjustment: account overstated vs bank statement."""
        account = MockAccount()
        payee = MockPayee()
        txn = MockTransaction(amount=D("-75.00"))
        svc = make_adjustment_service(account, payee, txn)

        await svc.create_adjustment(ACCOUNT_ID, D("-75.00"))

        kwargs = svc.transaction_repo.create.call_args.kwargs
        assert kwargs["amount"] == D("-75.00")

    async def test_zero_adjustment_when_already_balanced(self):
        account = MockAccount()
        payee = MockPayee()
        txn = MockTransaction(amount=D("0"))
        svc = make_adjustment_service(account, payee, txn)

        await svc.create_adjustment(ACCOUNT_ID, D("0"))

        kwargs = svc.transaction_repo.create.call_args.kwargs
        assert kwargs["amount"] == D("0")

    async def test_adjustment_is_cleared_not_reconciled(self):
        """
        Critical: adjustment is created as 'cleared' so finish() will mark it reconciled.
        If created as 'reconciled' it would already be locked; if 'uncleared' it would
        not be included in the cleared balance check.
        """
        account = MockAccount()
        payee = MockPayee()
        txn = MockTransaction(cleared="cleared")
        svc = make_adjustment_service(account, payee, txn)

        await svc.create_adjustment(ACCOUNT_ID, D("100.00"))

        kwargs = svc.transaction_repo.create.call_args.kwargs
        assert kwargs["cleared"] == "cleared"

    async def test_adjustment_is_uncategorized(self):
        """Adjustment transaction has no category (category_id=None)."""
        account = MockAccount()
        payee = MockPayee()
        txn = MockTransaction()
        svc = make_adjustment_service(account, payee, txn)

        await svc.create_adjustment(ACCOUNT_ID, D("50.00"))

        kwargs = svc.transaction_repo.create.call_args.kwargs
        assert kwargs["category_id"] is None

    async def test_adjustment_memo_is_automatic_message(self):
        account = MockAccount()
        payee = MockPayee()
        txn = MockTransaction()
        svc = make_adjustment_service(account, payee, txn)

        await svc.create_adjustment(ACCOUNT_ID, D("50.00"))

        kwargs = svc.transaction_repo.create.call_args.kwargs
        assert kwargs["memo"] == "Entered automatically by IGAB"

    async def test_adjustment_is_approved(self):
        account = MockAccount()
        payee = MockPayee()
        txn = MockTransaction()
        svc = make_adjustment_service(account, payee, txn)

        await svc.create_adjustment(ACCOUNT_ID, D("50.00"))

        kwargs = svc.transaction_repo.create.call_args.kwargs
        assert kwargs["approved"] is True

    async def test_payee_name_is_reconciliation_adjustment(self):
        """Specific payee name is created or reused so it's recognizable in history."""
        account = MockAccount()
        payee = MockPayee()
        txn = MockTransaction()
        svc = make_adjustment_service(account, payee, txn)

        await svc.create_adjustment(ACCOUNT_ID, D("100.00"))

        svc.payee_repo.find_or_create.assert_called_once_with(
            account.budget_id, "Reconciliation Balance Adjustment"
        )

    async def test_payee_id_used_on_transaction(self):
        """The payee's id (not name) is passed to the transaction."""
        account = MockAccount()
        payee = MockPayee()
        txn = MockTransaction()
        svc = make_adjustment_service(account, payee, txn)

        await svc.create_adjustment(ACCOUNT_ID, D("100.00"))

        kwargs = svc.transaction_repo.create.call_args.kwargs
        assert kwargs["payee_id"] == payee.id

    async def test_returns_created_transaction(self):
        account = MockAccount()
        payee = MockPayee()
        expected = MockTransaction(amount=D("200.00"))
        svc = make_adjustment_service(account, payee, expected)

        result = await svc.create_adjustment(ACCOUNT_ID, D("200.00"))

        assert result is expected

    async def test_budget_id_comes_from_account(self):
        """budget_id for the new transaction comes from the looked-up account."""
        account = MockAccount(budget_id=BUDGET_ID)
        payee = MockPayee()
        txn = MockTransaction()
        svc = make_adjustment_service(account, payee, txn)

        await svc.create_adjustment(ACCOUNT_ID, D("50.00"))

        kwargs = svc.transaction_repo.create.call_args.kwargs
        assert kwargs["budget_id"] == BUDGET_ID


class TestFinish:
    async def test_snapshot_created_with_correct_balances(self):
        """finish() records statement_balance and the cleared_balance from get_status."""
        snapshot = MockSnapshot()
        svc = make_finish_service(D("1200.00"), snapshot)

        await svc.finish(ACCOUNT_ID, D("1500.00"))

        svc.repo.create.assert_called_once()
        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["statement_balance"] == D("1500.00")
        assert kwargs["cleared_balance"] == D("1200.00")

    async def test_adjustment_amount_is_statement_minus_cleared(self):
        """adjustment_amount = statement_balance - cleared_balance."""
        snapshot = MockSnapshot()
        svc = make_finish_service(D("1200.00"), snapshot)

        await svc.finish(ACCOUNT_ID, D("1500.00"))

        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["adjustment_amount"] == D("300.00")  # 1500 - 1200

    async def test_adjustment_amount_negative_when_account_overstated(self):
        """Negative when cleared_balance > statement_balance."""
        snapshot = MockSnapshot()
        svc = make_finish_service(D("1200.00"), snapshot)

        await svc.finish(ACCOUNT_ID, D("1000.00"))

        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["adjustment_amount"] == D("-200.00")  # 1000 - 1200

    async def test_adjustment_amount_zero_when_perfectly_balanced(self):
        snapshot = MockSnapshot()
        svc = make_finish_service(D("1000.00"), snapshot)

        await svc.finish(ACCOUNT_ID, D("1000.00"))

        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["adjustment_amount"] == D("0")

    async def test_returns_created_snapshot(self):
        expected = MockSnapshot()
        svc = make_finish_service(D("1000.00"), expected)

        result = await svc.finish(ACCOUNT_ID, D("1000.00"))

        assert result is expected

    async def test_adjustment_transaction_auto_created_on_mismatch(self):
        """A statement/cleared mismatch auto-creates the adjustment and links
        it in the snapshot — reconciliation always locks a matching account."""
        snapshot = MockSnapshot()
        svc = make_finish_service(D("1200.00"), snapshot)

        await svc.finish(ACCOUNT_ID, D("1500.00"))

        svc.transaction_repo.create.assert_called_once()
        create_kwargs = svc.transaction_repo.create.call_args.kwargs
        assert create_kwargs["amount"] == D("300.00")
        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["adjustment_transaction_id"] == svc._test_adjustment.id

    async def test_no_adjustment_transaction_id_is_none(self):
        snapshot = MockSnapshot()
        svc = make_finish_service(D("1000.00"), snapshot)

        await svc.finish(ACCOUNT_ID, D("1000.00"))

        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["adjustment_transaction_id"] is None

    async def test_bulk_update_and_account_update_executed(self):
        """
        finish() must call session.execute for:
          1-3: get_status (3 queries)
          4: UPDATE Transaction SET cleared='reconciled'
          5: UPDATE Account SET last_reconciled_at=...
        """
        snapshot = MockSnapshot()
        svc = make_finish_service(D("1000.00"), snapshot)

        await svc.finish(ACCOUNT_ID, D("1000.00"))

        assert svc.session.execute.call_count == 5

    async def test_session_flushed(self):
        """Session must be flushed so all changes are committed atomically."""
        snapshot = MockSnapshot()
        svc = make_finish_service(D("1000.00"), snapshot)

        await svc.finish(ACCOUNT_ID, D("1000.00"))

        svc.session.flush.assert_called_once()

    async def test_snapshot_account_id_correct(self):
        snapshot = MockSnapshot()
        svc = make_finish_service(D("1000.00"), snapshot)

        await svc.finish(ACCOUNT_ID, D("1000.00"))

        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["account_id"] == ACCOUNT_ID

    async def test_cleared_balance_source_is_get_status(self):
        """cleared_balance in snapshot comes from get_status, not statement_balance."""
        snapshot = MockSnapshot()
        svc = make_finish_service(D("800.00"), snapshot)  # cleared_balance = 800

        await svc.finish(ACCOUNT_ID, D("1000.00"))  # statement = 1000

        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["cleared_balance"] == D("800.00")
        assert kwargs["statement_balance"] == D("1000.00")

    async def test_zero_cleared_balance_empty_account(self):
        """finish() works on an account with no cleared transactions yet."""
        snapshot = MockSnapshot(cleared_balance=D("0"))
        svc = make_finish_service(D("0"), snapshot)

        result = await svc.finish(ACCOUNT_ID, D("0"))

        assert result is snapshot
        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["adjustment_amount"] == D("0")


class TestGetHistory:
    async def test_history_delegated_to_repo(self):
        """get_history simply delegates to the reconciliation repo."""
        snap1 = MockSnapshot()
        snap2 = MockSnapshot()
        repo = MagicMock()
        repo.get_history = AsyncMock(return_value=[snap1, snap2])

        svc = ReconciliationService(
            session=AsyncMock(),
            repo=repo,
            account_repo=MagicMock(),
            payee_repo=MagicMock(),
            transaction_repo=MagicMock(),
        )

        result = await svc.get_history(ACCOUNT_ID)

        repo.get_history.assert_called_once_with(ACCOUNT_ID)
        assert result == [snap1, snap2]

    async def test_empty_history(self):
        repo = MagicMock()
        repo.get_history = AsyncMock(return_value=[])

        svc = ReconciliationService(
            session=AsyncMock(),
            repo=repo,
            account_repo=MagicMock(),
            payee_repo=MagicMock(),
            transaction_repo=MagicMock(),
        )

        result = await svc.get_history(ACCOUNT_ID)
        assert result == []
