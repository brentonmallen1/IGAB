"""
Tests for payee auto-categorization memory in TransactionService.create().

Rules:
  1. When a transaction is created with a payee but NO category, and the payee has a
     default_category_id, that default is applied to the transaction automatically.
  2. When a transaction is created with both a payee AND a category, the provided
     category is used and the payee's default_category_id is updated to that category.
  3. When a payee has no default_category_id and no category is provided, the
     system falls back to the most common historical category for that payee.
     If there is no historical category either, the transaction has no category.
  4. When there is no payee at all, no category is inferred.

These rules allow the system to "remember" categorizations from past transactions
so users are not forced to re-categorize recurring payees.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call

import pytest

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


@dataclass
class MockPayee:
    id: uuid.UUID = PAYEE_ID
    default_category_id: uuid.UUID | None = None


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
    txn_repo.create = AsyncMock(return_value=txn)
    txn_repo.get_most_common_category_for_payee = AsyncMock(return_value=None)

    session = AsyncMock()
    session.get = AsyncMock(return_value=payee)

    return TransactionService(
        session=session,
        transaction_repo=txn_repo,
        account_repo=account_repo,
        category_repo=MagicMock(),
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


class TestPayeeDefaultCategoryApplied:
    """When no category is given but payee has a default, the default is used."""

    async def test_payee_name_with_default_category_applied(self):
        """Creating via payee_name: default_category_id flows to transaction."""
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Grocery Store")
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == DEFAULT_CAT_ID

    async def test_payee_id_with_default_category_applied(self):
        """Creating via payee_id: default_category_id flows to transaction."""
        payee = MockPayee(id=PAYEE_ID, default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_id=PAYEE_ID)
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == DEFAULT_CAT_ID

    async def test_payee_with_no_default_uses_no_category(self):
        """If payee has no default category, transaction has no category."""
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


class TestExplicitCategoryOverridesDefault:
    """When user explicitly provides a category, it overrides the payee default."""

    async def test_explicit_category_beats_payee_default(self):
        """Explicit category_id takes precedence over payee.default_category_id."""
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Grocery Store", category_id=EXPLICIT_CAT_ID)
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == EXPLICIT_CAT_ID

    async def test_explicit_category_does_not_overwrite_existing_default(self):
        """The payee memory is learned once; a differently-categorized
        transaction must not silently rewrite it."""
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Grocery Store", category_id=EXPLICIT_CAT_ID)
        txn_call = await svc.create(BUDGET_ID, data)
        assert txn_call is not None

        svc.payee_repo.update.assert_not_called()

    async def test_explicit_category_learned_when_payee_has_no_default(self):
        """First categorization teaches the payee its default."""
        payee = MockPayee(default_category_id=None)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Grocery Store", category_id=EXPLICIT_CAT_ID)
        await svc.create(BUDGET_ID, data)

        svc.payee_repo.update.assert_called_once_with(
            payee.id, default_category_id=EXPLICIT_CAT_ID
        )

    async def test_no_explicit_category_does_not_update_payee_default(self):
        """When no category is provided (using default), payee memory is NOT re-updated."""
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Grocery Store")  # no explicit category
        await svc.create(BUDGET_ID, data)

        svc.payee_repo.update.assert_not_called()

    async def test_no_category_no_payee_no_update(self):
        """No payee means no memory update."""
        svc = make_service(payee=None)

        data = base_txn_data()
        await svc.create(BUDGET_ID, data)

        svc.payee_repo.update.assert_not_called()


class TestPayeeDefaultCategoryAmounts:
    """Auto-categorization does not affect transaction amounts."""

    async def test_amount_is_preserved_regardless_of_default_category(self):
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Grocery Store", amount=D("-87.43"))
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["amount"] == D("-87.43")
        assert create_call.kwargs["category_id"] == DEFAULT_CAT_ID

    async def test_inflow_with_default_category_preserved(self):
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Employer", amount=D("3000.00"))
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["amount"] == D("3000.00")

    async def test_zero_amount_with_default_category(self):
        payee = MockPayee(default_category_id=DEFAULT_CAT_ID)
        svc = make_service(payee)

        data = base_txn_data(payee_name="Adjustment", amount=D("0.00"))
        await svc.create(BUDGET_ID, data)

        create_call = svc.transaction_repo.create.call_args
        assert create_call.kwargs["category_id"] == DEFAULT_CAT_ID

    async def test_different_default_categories_for_different_payees(self):
        """Each payee has its own default — test isolation by running both."""
        cat_a = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000000")
        cat_b = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000000")

        payee_a = MockPayee(id=uuid.uuid4(), default_category_id=cat_a)
        svc_a = make_service(payee_a)
        data_a = base_txn_data(payee_name="Payee A")
        await svc_a.create(BUDGET_ID, data_a)
        call_a = svc_a.transaction_repo.create.call_args
        assert call_a.kwargs["category_id"] == cat_a

        payee_b = MockPayee(id=uuid.uuid4(), default_category_id=cat_b)
        svc_b = make_service(payee_b)
        data_b = base_txn_data(payee_name="Payee B")
        await svc_b.create(BUDGET_ID, data_b)
        call_b = svc_b.transaction_repo.create.call_args
        assert call_b.kwargs["category_id"] == cat_b
