"""
Edge case tests for budget calculations, covering:
  - YNAB import vs native budget Income group setup
  - Transaction cleared-state impact on TBA
  - Transfer handling
  - Category/account combinations that could distort TBA
  - Known inconsistencies between account_repo and transaction_repo filters
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

    async def _sum_after_month(budget_id, month):
        return sum(
            (
                a.assigned
                for assigns in assignments_by_category.values()
                for a in assigns
                if a.month > month
            ),
            D("0"),
        )

    assignment_repo.sum_after_month = AsyncMock(side_effect=_sum_after_month)

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


class TestYNABImportVsNative:
    """
    Native budgets create an 'Income' group with is_system=True from the start.
    YNAB imports map the "Inflow" category group → "Income" and set is_system=True.
    Before migration c3d4e5f6a7b8, some YNAB-imported budgets had is_system=False on
    the Income group, causing massive TBA distortion (income activity reduced TBA).
    """

    async def test_native_income_group_with_is_system_does_not_reduce_tba(self):
        """Native budget: Income group with is_system=True is properly excluded."""
        checking = MockAccount()
        income_grp = MockCategoryGroup(name="Income", is_system=True)
        expense_grp = MockCategoryGroup(name="Food", is_system=False)
        rta_cat = MockCategory(category_group_id=income_grp.id)  # Ready to Assign
        food_cat = MockCategory(category_group_id=expense_grp.id)

        svc = make_service(
            accounts=[checking],
            balances={checking.id: D("3000.00")},
            categories=[rta_cat, food_cat],
            groups=[income_grp, expense_grp],
            assignments_by_category={
                food_cat.id: [
                    MockAssignment(category_id=food_cat.id, month=JAN, assigned=D("500.00"))
                ],
            },
            activity_by_category={
                rta_cat.id: {JAN: D("3000.00")},  # income transactions
                food_cat.id: {JAN: D("-200.00")},
            },
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # Income activity (3000) excluded; food available = 500-200=300
        # TBA = 3000 - 300 = 2700
        assert result.to_be_assigned == D("2700.00")

    async def test_ynab_import_income_group_is_system_true(self):
        """
        YNAB import: 'Inflow: Ready to Assign' maps to Income with is_system=True.
        Verify same exclusion behavior as native.
        """
        checking = MockAccount()
        # Simulates correctly imported YNAB budget
        income_grp = MockCategoryGroup(name="Income", is_system=True)
        rta_cat = MockCategory(category_group_id=income_grp.id)

        svc = make_service(
            accounts=[checking],
            balances={checking.id: D("5000.00")},
            categories=[rta_cat],
            groups=[income_grp],
            activity_by_category={rta_cat.id: {JAN: D("5000.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # Income excluded — TBA = entire account balance
        assert result.to_be_assigned == D("5000.00")

    async def test_ynab_import_missing_is_system_distorts_tba(self):
        """
        Documents the pre-migration bug: if YNAB-imported Income group has is_system=False,
        income transactions are subtracted from TBA, inflating it by income amount.

        This is why migration c3d4e5f6a7b8 and importer.py were fixed.
        """
        checking = MockAccount()
        misconfigured_grp = MockCategoryGroup(name="Income", is_system=False)
        rta_cat = MockCategory(category_group_id=misconfigured_grp.id)
        expense_grp = MockCategoryGroup(name="Food", is_system=False)
        food_cat = MockCategory(category_group_id=expense_grp.id)

        svc = make_service(
            accounts=[checking],
            balances={checking.id: D("3000.00")},
            categories=[rta_cat, food_cat],
            groups=[misconfigured_grp, expense_grp],
            assignments_by_category={
                food_cat.id: [
                    MockAssignment(category_id=food_cat.id, month=JAN, assigned=D("500.00"))
                ],
            },
            activity_by_category={
                rta_cat.id: {JAN: D("3000.00")},
                food_cat.id: {JAN: D("-200.00")},
            },
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # Bug: income available=3000 subtracted from TBA
        # TBA = 3000 - 3000 (income) - 300 (food) = -300 (should be 2700)
        assert result.to_be_assigned == D("-300.00")


class TestTransactionClearedStateImpact:
    """
    account_repo.get_balance EXCLUDES pending transactions.
    transaction_repo.sum_all_categories_by_month INCLUDES all states (including pending).

    This inconsistency means a pending categorized transaction will:
      - NOT affect account balance (correctly excluded)
      - BUT will affect category activity (incorrectly included)
      → TBA is artificially reduced when pending transactions have categories

    These tests document this behavior so it is visible if the inconsistency is fixed.
    """

    async def test_pending_transaction_excluded_from_account_balance(self):
        """
        The account repo correctly excludes pending transactions.
        We verify the service correctly uses the filtered balance.

        Scenario: account has $1000 of confirmed transactions + $200 pending.
        account_repo.get_balance returns $1000 (excludes pending).
        TBA should reflect $1000, not $1200.
        """
        acct = MockAccount()
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},  # pending $200 already excluded by repo
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("1000.00")

    async def test_pending_transaction_in_category_inflates_activity(self):
        """
        The transaction repo INCLUDES pending in category activity (current behavior).

        Scenario: $100 assigned to groceries, $50 pending groceries transaction.
        - account_repo.get_balance: $950 (pending excluded → $1000 base - $50 spent = $950... wait)

        More precisely: account has $1000, pending -$50 groceries txn:
          - account balance = $1000 (pending excluded)
          - groceries activity = -$50 (pending included)
          - groceries available = $100 - $50 = $50
          - TBA = $1000 - $50 = $950 ← $50 more than expected

        Without pending: TBA would be $1000 - $100 = $900.
        With pending included in activity: TBA = $1000 - $50 = $950 (inflated by $50).
        """
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("100.00"))

        svc = make_service(
            accounts=[acct],
            # Account balance: $1000 base, pending -$50 excluded = $1000
            balances={acct.id: D("1000.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
            # Activity includes pending -$50 (current repo behavior)
            activity_by_category={cat.id: {JAN: D("-50.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # groceries available = 100 - 50 = 50; TBA = 1000 - 50 = 950
        # If pending were EXCLUDED from activity (consistent with account): TBA = 1000 - 100 = 900
        assert result.to_be_assigned == D("950.00")

    async def test_uncleared_transaction_counts_in_both_balance_and_activity(self):
        """
        Uncleared transactions are counted in BOTH account balance AND category activity
        → TBA remains consistent (as expected).
        """
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("200.00"))

        svc = make_service(
            accounts=[acct],
            # Account balance includes uncleared -$80
            balances={acct.id: D("920.00")},  # $1000 - $80 uncleared
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
            # Activity includes uncleared -$80
            activity_by_category={cat.id: {JAN: D("-80.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # cat available = 200 - 80 = 120; TBA = 920 - 120 = 800
        assert result.to_be_assigned == D("800.00")

    async def test_reconciled_transaction_counts_in_both(self):
        """Reconciled transactions behave identically to cleared for TBA purposes."""
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("500.00"))

        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("700.00")},  # $1000 - $300 reconciled
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
            activity_by_category={cat.id: {JAN: D("-300.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # cat available = 500 - 300 = 200; TBA = 700 - 200 = 500
        assert result.to_be_assigned == D("500.00")


class TestTransferScenarios:
    """
    Transfers between on-budget accounts should be TBA-neutral (money moves, not created/destroyed).
    Transfer to/from off-budget account affects TBA (money leaves/enters the tracked pool).
    """

    async def test_transfer_between_on_budget_accounts_is_neutral(self):
        """
        $500 transfer from Checking to Savings (both on-budget):
          - Checking: $1500 → $1000
          - Savings: $0 → $500
          - Total on-budget: $1500 (unchanged)
          - TBA unchanged
        """
        checking = MockAccount()
        savings = MockAccount()
        svc = make_service(
            accounts=[checking, savings],
            balances={checking.id: D("1000.00"), savings.id: D("500.00")},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # Both accounts sum to $1500; no categories → TBA = $1500
        assert result.to_be_assigned == D("1500.00")

    async def test_transfer_to_off_budget_reduces_tracked_total(self):
        """
        Transfer $200 from on-budget Checking to off-budget savings account:
          - Checking: $1000 → $800 (outflow counted)
          - Off-budget savings: not counted in TBA
        """
        checking = MockAccount(on_budget=True)
        off_savings = MockAccount(on_budget=False)
        svc = make_service(
            accounts=[checking, off_savings],
            balances={checking.id: D("800.00"), off_savings.id: D("200.00")},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("800.00")

    async def test_uncategorized_transaction_in_account_not_in_categories(self):
        """
        Uncategorized transactions (no category assigned) count toward account balance
        but not toward any category balance → they show up as TBA.
        """
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("500.00"))

        svc = make_service(
            accounts=[acct],
            # Account has $1000 including $100 uncategorized transaction
            balances={acct.id: D("1000.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
            # Category only has $400 activity (not including the uncategorized $100)
            activity_by_category={cat.id: {JAN: D("-400.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # cat available = 500 - 400 = 100; TBA = 1000 - 100 = 900
        # The $100 uncategorized raises TBA (shows as "needs to be categorized")
        assert result.to_be_assigned == D("900.00")


class TestCrossMonthTBAConsistency:
    """
    TBA calculated for a month should be consistent across months when no new money
    is introduced and all money is assigned. Tests verify the floor simulation
    does not artificially distort TBA calculations over time.
    """

    async def test_tba_with_floor_overspend_absorbed(self):
        """
        After a month where a category overspends, the overspend is absorbed from TBA.

        Setup:
          - Account: $1000
          - Jan: $1000 assigned to groceries, -$1100 activity → overspend $100
          - Floor: groceries carryover = 0 (overspend covered from TBA)
          - Feb: $0 assigned, $0 activity

        Feb TBA = account_balance ($900) - groceries_available ($0) = $900
        The $100 overspend reduced account by $100 and TBA absorbs the mismatch.
        """
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        jan_assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("1000.00"))
        feb_assign = MockAssignment(category_id=cat.id, month=FEB, assigned=D("0.00"))

        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("900.00")},  # $1000 - $1100 spend + $1000... actually:
            # Simpler: account started with $2000, spent $1100, net $900
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [jan_assign, feb_assign]},
            activity_by_category={cat.id: {JAN: D("-1100.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, FEB)
        # Jan: 0+1000-1100=-100, carryover=0; Feb: 0+0+0=0 → cat available=0
        # TBA = 900 - 0 = 900
        assert result.to_be_assigned == D("900.00")

    async def test_tba_stable_when_all_money_assigned(self):
        """
        Ideal state: all account money is assigned to categories.
        Spending reduces both account balance and category available by the same amount.
        TBA remains at 0.
        """
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        jan_assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("1000.00"))

        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("600.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [jan_assign]},
            activity_by_category={cat.id: {JAN: D("-400.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # cat available = 1000 - 400 = 600; TBA = 600 - 600 = 0
        assert result.to_be_assigned == D("0")
