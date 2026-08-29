"""
Tests for payee auto-categorization memory in TransactionService.create().

Rules:
  1. When a transaction is created with a payee but NO category, the system uses
     the most recent category from that payee's transaction history.
  2. If there is no transaction history, it falls back to payee.default_category_id.
  3. When a transaction is created with an explicit category, that category is used.
  4. When there is no payee at all, no category is inferred.

These rules allow the system to adapt to changing categorization patterns
without requiring manual management of payee defaults.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from igab.services.transaction_service import TransactionCreate, TransactionService

BUDGET_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
PAYEE_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
DEFAULT_CAT_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")
EXPLICIT_CAT_ID = uuid.UUID("00000000-0000-0000-0000-000000000005")


def D(s: str) -> Decimal:
    return Decimal(s)


@dataclass
class MockAccount:
    id: uuid.UUID = ACCOUNT_ID
    budget_id: uuid.UUID = BUDGET_ID
    # Auto-categorize is offered only to on-budget rows; these tests are
    # about the payee-memory rule, so the account is in scope for it.
    on_budget: bool = True


@dataclass
class MockPayee:
    id: uuid.UUID = PAYEE_ID
    default_category_id: uuid.UUID | None = None


@dataclass
class MockCategory:
    id: uuid.UUID = DEFAULT_CAT_ID


@dataclass
class MockTransaction:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    budget_id: uuid.UUID = BUDGET_ID
    account_id: uuid.UUID = ACCOUNT_ID
    category_id: uuid.UUID | None = None
    payee_id: uuid.UUID | None = None
    cleared: str = "uncleared"
    transfer_id: uuid.UUID | None = None
    parent_transaction_id: uuid.UUID | None = None
    is_split: bool = False


def make_service(payee: MockPayee | None) -> TransactionService:
    account = MockAccount()
    txn = MockTransaction()

    account_repo = MagicMock()
    account_repo.get_or_raise = AsyncMock(return_value=account)

    payee_repo = MagicMock()
    # _resolve_payee calls find_by_name first, then find_best_match, then create
    payee_repo.find_by_name = AsyncMock(return_value=payee)
    payee_repo.find_best_match = AsyncMock(return_value=None)
    payee_repo.create = AsyncMock(return_value=payee)
    payee_repo.update = AsyncMock()

    txn_repo = MagicMock()
    txn_repo.refresh = AsyncMock()
    txn_repo.create = AsyncMock(return_value=txn)
    txn_repo.get_most_recent_category_for_payee = AsyncMock(return_value=None)

    # The default-category fallback is liveness-checked, so a deleted category
    # can never be handed to a brand-new transaction. Return the category the
    # payee names; the deleted case (get -> None) is covered end to end in
    # tests/integration/test_category_delete.py.
    category_repo = MagicMock()
    category_repo.get = AsyncMock(
        return_value=(
            MockCategory(id=payee.default_category_id)
            if payee is not None and payee.default_category_id is not None
            else None
        )
    )

    session = AsyncMock()
    session.get = AsyncMock(return_value=payee)
    # require_in_budget runs session.execute(...).scalar_one_or_none(); return a
    # truthy row so body-supplied ids validate as belonging to the budget.
    ownership_result = MagicMock()
    ownership_result.scalar_one_or_none = MagicMock(return_value=MagicMock())
    session.execute = AsyncMock(return_value=ownership_result)

    return TransactionService(
        session=session,
        transaction_repo=txn_repo,
        account_repo=account_repo,
        category_repo=category_repo,
        payee_repo=payee_repo,
    )


def base_txn_data(**kwargs) -> TransactionCreate:
    defaults = dict(
        account_id=ACCOUNT_ID,
        date=date(2026, 1, 15),
        amount=D("-25.00"),
        cleared="uncleared",
        approved=True,
    )
    defaults.update(kwargs)
    return TransactionCreate(**defaults)


RECENT_CAT_ID = uuid.UUID("00000000-0000-0000-0000-000000000006")


class TestMostRecentCategoryApplied:
    """Auto-categorization uses the most recent category for the payee."""

    async def test_uses_most_recent_category_over_default(self):
        """Most recent category takes precedence over default_category_id."""
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)
        svc.transaction_repo.get_most_recent_category_for_payee = AsyncMock(
            return_value=RECENT_CAT_ID
        )

        data = base_txn_data(payee_name="Grocery Store")
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == RECENT_CAT_ID

    async def test_falls_back_to_default_when_no_history(self):
        """Falls back to default_category_id when no transaction history exists."""
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)
        svc.transaction_repo.get_most_recent_category_for_payee = AsyncMock(return_value=None)

        data = base_txn_data(payee_name="Grocery Store")
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == DEFAULT_CAT_ID

    async def test_no_category_when_no_history_and_no_default(self):
        """No category when payee has neither history nor default."""
        payee = MockPayee(default_category_id=None)
        svc = make_service(payee)

        data = base_txn_data(payee_name="New Payee")
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] is None

    async def test_no_payee_uses_no_category(self):
        """No payee at all → no category inferred."""
        svc = make_service(payee=None)

        data = base_txn_data()  # no payee fields
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] is None


class TestExplicitCategoryOverridesAll:
    """When user explicitly provides a category, it overrides auto-categorization."""

    async def test_explicit_category_beats_most_recent(self):
        """Explicit category_id takes precedence over most recent."""
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)
        svc.transaction_repo.get_most_recent_category_for_payee = AsyncMock(
            return_value=RECENT_CAT_ID
        )

        data = base_txn_data(payee_name="Grocery Store", category_id=EXPLICIT_CAT_ID)
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == EXPLICIT_CAT_ID

    async def test_explicit_category_does_not_update_payee(self):
        """Explicit category does not update payee default_category_id."""
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Grocery Store", category_id=EXPLICIT_CAT_ID)
        await svc.create(BUDGET_ID, data)

        svc.payee_repo.update.assert_not_called()

    async def test_no_category_no_payee_no_update(self):
        """No payee means no memory update."""
        svc = make_service(payee=None)

        data = base_txn_data()
        await svc.create(BUDGET_ID, data)

        svc.payee_repo.update.assert_not_called()


class TestAutoCategoryAmounts:
    """Auto-categorization does not affect transaction amounts."""

    async def test_amount_is_preserved(self):
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Grocery Store", amount=D("-87.43"))
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["amount"] == D("-87.43")

    async def test_inflow_with_auto_category_preserved(self):
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Employer", amount=D("3000.00"))
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["amount"] == D("3000.00")

    async def test_zero_amount_with_auto_category(self):
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Adjustment", amount=D("0.00"))
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == DEFAULT_CAT_ID
