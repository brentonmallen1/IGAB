"""
Specification tests for BudgetService category-balance math given repo outputs.

TransactionRepository.sum_all_categories_by_month specification (enforced by
integration tests in tests/integration/test_category_activity.py and
test_pending_consistency.py against a real database):
  - Groups transactions by (category_id, year, month)
  - INCLUDES: leaf rows only (is_split == False) — plain transactions and
    split children; split parents carry no category
  - EXCLUDES: pending transactions (cleared == 'pending'), matching
    account_repo.get_balance so TBA never skews while a bank auth is pending
  - EXCLUDES: soft-deleted transactions (is_deleted=True)
  - Returns {category_id: {month_start: total_amount}}

The tests below mock the repo and verify only the BudgetService formula:
available carryover flooring, TBA composition, and system-group exclusion.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from igab.services.budget_service import BudgetService

BUDGET_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
JAN = date(2026, 1, 1)
FEB = date(2026, 2, 1)


def D(s: str) -> Decimal:
    return Decimal(s)


@dataclass
class MockAccount:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    on_budget: bool = True
    is_closed: bool = False
    # The summary's card block reads classification; "asset" keeps these
    # tests about their own subject — no card accounts, block short-circuits.
    classification: str = "asset"


@dataclass
class MockCategoryGroup:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "Group"
    is_system: bool = False


@dataclass
class MockCategory:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    category_group_id: uuid.UUID = field(default_factory=uuid.uuid4)
    # Card set-aside envelopes are linked; None keeps these ordinary.
    linked_account_id: uuid.UUID | None = None


@dataclass
class MockAssignment:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    category_id: uuid.UUID = field(default_factory=uuid.uuid4)
    month: date = JAN
    assigned: Decimal = D("0")


def make_service(
    accounts=None,
    balances=None,
    categories=None,
    groups=None,
    assignments_by_category=None,
    activity_by_category=None,
):
    accounts = accounts or []
    balances = balances or {}
    categories = categories or []
    groups = groups or []
    assignments_by_category = assignments_by_category or {}
    activity_by_category = activity_by_category or {}

    account_repo = MagicMock()

    async def _sum_on_budget_balance(budget_id, as_of):
        # Every on-budget account funds TBA, closed ones included — see
        # AccountRepository.sum_on_budget_balance.
        return sum((balances.get(a.id, D("0")) for a in accounts if a.on_budget), D("0"))

    account_repo.sum_on_budget_balance = AsyncMock(side_effect=_sum_on_budget_balance)
    account_repo.get_all = AsyncMock(return_value=accounts)

    category_repo = MagicMock()
    category_repo.get_all = AsyncMock(return_value=categories)

    category_group_repo = MagicMock()
    category_group_repo.get_all = AsyncMock(return_value=groups)

    assignment_repo = MagicMock()

    async def _get_for_category(cat_id, through_month=None):
        return assignments_by_category.get(cat_id, [])

    assignment_repo.get_for_category = AsyncMock(side_effect=_get_for_category)
    assignment_repo.sum_after_month = AsyncMock(return_value=Decimal("0"))

    transaction_repo = MagicMock()

    async def _sum_all(cat_ids, end_date):
        return {cat_id: activity_by_category.get(cat_id, {}) for cat_id in cat_ids}

    transaction_repo.sum_all_categories_by_month = AsyncMock(side_effect=_sum_all)

    return BudgetService(
        account_repo=account_repo,
        category_repo=category_repo,
        category_group_repo=category_group_repo,
        assignment_repo=assignment_repo,
        transaction_repo=transaction_repo,
    )


class TestCategoryActivityAggregation:
    """
    Verify that category activity (as returned by the repo) is correctly summed
    per-month and applied to the category balance calculation.
    """

    async def test_single_month_single_category_activity(self):
        """Activity for one category in one month is applied correctly."""
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("200.00"))

        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("800.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
            activity_by_category={cat.id: {JAN: D("-150.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # cat available = 200 - 150 = 50; TBA = 800 - 50 = 750
        assert result.to_be_assigned == D("750.00")
        jan_bal = next(b for b in result.category_balances if b.category_id == cat.id)
        assert jan_bal.activity == D("-150.00")
        assert jan_bal.available == D("50.00")

    async def test_multi_month_activity_accumulated_through_floor(self):
        """Activity across months is accumulated with floor simulation."""
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        jan_assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("300.00"))
        feb_assign = MockAssignment(category_id=cat.id, month=FEB, assigned=D("100.00"))

        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("700.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [jan_assign, feb_assign]},
            # Jan: 300-350=-50 → floored to 0; Feb: 0+100-80=20
            activity_by_category={cat.id: {JAN: D("-350.00"), FEB: D("-80.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, FEB)
        feb_bal = next(b for b in result.category_balances if b.category_id == cat.id)
        assert feb_bal.available == D("20.00")
        assert feb_bal.activity == D("-80.00")  # only Feb's activity in the 'activity' field

    async def test_zero_activity_month_has_no_effect(self):
        """A month with no transactions for a category still carries forward correctly."""
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        jan_assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("100.00"))

        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [jan_assign]},
            activity_by_category={cat.id: {}},  # no activity
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        jan_bal = next(b for b in result.category_balances if b.category_id == cat.id)
        assert jan_bal.available == D("100.00")
        assert jan_bal.activity == D("0")

    async def test_split_children_activity_aggregated_not_parent(self):
        """
        Spec: split parents excluded (parent_transaction_id IS NULL).
        Activity should reflect sum of split children, not the parent amount.

        Example: $300 split purchase with $200 to groceries and $100 to dining.
        Groceries activity should show -$200, not -$300.
        """
        acct = MockAccount()
        grp = MockCategoryGroup()
        groceries = MockCategory(category_group_id=grp.id)
        dining = MockCategory(category_group_id=grp.id)
        g_assign = MockAssignment(category_id=groceries.id, month=JAN, assigned=D("300.00"))
        d_assign = MockAssignment(category_id=dining.id, month=JAN, assigned=D("150.00"))

        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("700.00")},  # $1000 - $300 split purchase
            categories=[groceries, dining],
            groups=[grp],
            assignments_by_category={
                groceries.id: [g_assign],
                dining.id: [d_assign],
            },
            # Repo returns split children's amounts per category (not parent's total)
            activity_by_category={
                groceries.id: {JAN: D("-200.00")},
                dining.id: {JAN: D("-100.00")},
            },
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        g_bal = next(b for b in result.category_balances if b.category_id == groceries.id)
        d_bal = next(b for b in result.category_balances if b.category_id == dining.id)
        assert g_bal.available == D("100.00")  # 300 - 200
        assert d_bal.available == D("50.00")  # 150 - 100


class TestPendingConsistency:
    """
    Pending transactions are excluded from BOTH account balances and category
    activity (enforced in SQL; see tests/integration/test_pending_consistency.py).
    Given consistent repo feeds, TBA equals the hand-computed value and a
    transaction posting moves both sides at once.
    """

    async def test_posted_transaction_moves_account_and_activity_together(self):
        """A posted -$100 appears in both feeds: TBA = 900 - (500-100) = 500."""
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("500.00"))

        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("900.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
            activity_by_category={cat.id: {JAN: D("-100.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("500.00")

    async def test_pending_transaction_moves_neither_side(self):
        """While pending, the repo feeds exclude the amount from both sides:
        balance stays $1000, activity stays 0, TBA = 1000 - 500 = 500."""
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("500.00"))

        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
            activity_by_category={cat.id: {}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("500.00")
