"""
Specification tests for account_repo.get_balance cleared-state filtering.

These tests document the REQUIRED behavior of AccountRepository.get_balance and verify
that BudgetService correctly handles the filtered values. Integration tests (requiring
a real database) would test the actual SQL; these unit tests specify the contract.

AccountRepository.get_balance specification:
  - INCLUDES: uncleared, cleared, reconciled transactions
  - EXCLUDES: pending transactions
  - EXCLUDES: soft-deleted transactions (is_deleted=True)
  - EXCLUDES: split parent transactions (parent_transaction_id IS NOT NULL)
  - Only counts transactions for the given account_id

This matches YNAB's "working balance" (cleared/posted balance includes uncleared
but excludes pending/scheduled). Pending transactions are visible in the UI but
do not affect the working balance used for TBA calculation.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from igab.services.budget_service import BudgetService

BUDGET_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
JAN = date(2026, 1, 1)


def D(s: str) -> Decimal:
    return Decimal(s)


@dataclass
class MockAccount:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    on_budget: bool = True
    is_closed: bool = False


def make_service_with_balance(account: MockAccount, balance: Decimal) -> BudgetService:
    """Service where account_repo.get_balance returns a pre-computed value."""
    account_repo = MagicMock()
    account_repo.get_on_budget = AsyncMock(return_value=[account])
    account_repo.get_balance = AsyncMock(return_value=balance)

    return BudgetService(
        account_repo=account_repo,
        category_repo=MagicMock(get_all=AsyncMock(return_value=[])),
        category_group_repo=MagicMock(get_all=AsyncMock(return_value=[])),
        assignment_repo=MagicMock(),
        transaction_repo=MagicMock(
            sum_all_categories_by_month=AsyncMock(return_value={})
        ),
    )


class TestAccountBalanceClearedStates:
    """
    Verify TBA reflects the correct account balance based on cleared state filtering.
    Each test simulates the balance that account_repo.get_balance SHOULD return
    for a given set of transactions.
    """

    async def test_pending_transaction_excluded_balance_unchanged(self):
        """
        Spec: pending transactions EXCLUDED from balance.
        When the repo correctly excludes a pending -$500 transaction,
        the account balance (and TBA) reflects only confirmed transactions.
        """
        acct = MockAccount()
        # Account has $1000 in confirmed transactions; $500 pending debit not counted
        svc = make_service_with_balance(acct, D("1000.00"))
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("1000.00")

    async def test_uncleared_transaction_included_in_balance(self):
        """
        Spec: uncleared transactions ARE included in balance.
        An uncleared -$200 debit reduces the account balance immediately
        (it represents spending that has occurred but not yet cleared the bank).
        """
        acct = MockAccount()
        # $1000 starting - $200 uncleared debit = $800 balance
        svc = make_service_with_balance(acct, D("800.00"))
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("800.00")

    async def test_cleared_transaction_included_in_balance(self):
        """
        Spec: cleared transactions ARE included in balance.
        A cleared -$150 debit reduces the account balance.
        """
        acct = MockAccount()
        svc = make_service_with_balance(acct, D("850.00"))
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("850.00")

    async def test_reconciled_transaction_included_in_balance(self):
        """
        Spec: reconciled transactions ARE included in balance.
        Reconciled transactions have been verified against bank statements.
        """
        acct = MockAccount()
        svc = make_service_with_balance(acct, D("750.00"))
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("750.00")

    async def test_mixed_states_balance_excludes_only_pending(self):
        """
        Spec: account with multiple transactions of different states.
        Starting $2000:
          - cleared -$300       → included, balance $1700
          - reconciled -$200    → included, balance $1500
          - uncleared -$100     → included, balance $1400
          - pending -$500       → EXCLUDED, balance stays $1400

        account_repo.get_balance should return $1400 (not $900 which would include pending).
        """
        acct = MockAccount()
        svc = make_service_with_balance(acct, D("1400.00"))  # pending excluded
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("1400.00")


class TestSplitTransactionHandling:
    """
    Split transactions: the parent transaction holds metadata, child transactions
    hold the actual amounts (with categories). The parent is excluded from balance
    to avoid double-counting. Only split children are summed.

    Spec: parent_transaction_id IS NULL in get_balance → split parents excluded.
    """

    async def test_split_parent_excluded_children_included(self):
        """
        A $300 parent split into two $150 children:
          - Parent: excluded from balance (parent_transaction_id IS NULL filter)
          - Child 1 $150 (cat A): included
          - Child 2 $150 (cat B): included
          - Net balance effect: -$300 (correct)

        The repo returns -$300 because it sums the two children, not the parent.
        """
        acct = MockAccount()
        # Repo correctly returns sum of split children, not parent
        svc = make_service_with_balance(acct, D("700.00"))  # $1000 - $300 split
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("700.00")


class TestSoftDeletedTransactions:
    """
    Soft-deleted transactions (is_deleted=True) must be excluded from all calculations.
    """

    async def test_soft_deleted_transaction_excluded_from_balance(self):
        """
        A deleted -$200 transaction should not reduce balance.
        The repo should return $1000 as if the deleted transaction never existed.
        """
        acct = MockAccount()
        svc = make_service_with_balance(acct, D("1000.00"))  # deleted txn excluded
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("1000.00")
