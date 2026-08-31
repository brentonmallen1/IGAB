"""
TBA (To Be Assigned) calculation tests for BudgetService.get_budget_summary.

Formula: TBA = sum(on-budget account balances) - sum(non-system category available balances)

System (Income) categories are excluded from the category sum because income transactions
raise the account balance directly; including them would double-count.
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


class TestTBAWithNoData:
    async def test_no_accounts_no_categories(self):
        svc = make_service()
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("0")

    async def test_single_account_no_categories(self):
        acct = MockAccount()
        svc = make_service(accounts=[acct], balances={acct.id: D("1000.00")})
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("1000.00")

    async def test_multiple_accounts_balances_sum(self):
        a1, a2, a3 = MockAccount(), MockAccount(), MockAccount()
        svc = make_service(
            accounts=[a1, a2, a3],
            balances={a1.id: D("500.00"), a2.id: D("300.00"), a3.id: D("200.00")},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("1000.00")

    async def test_account_with_negative_balance(self):
        acct = MockAccount()
        svc = make_service(accounts=[acct], balances={acct.id: D("-200.00")})
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("-200.00")


class TestTBAWithAssignments:
    async def test_assigned_amount_reduces_tba(self):
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("400.00"))
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("600.00")

    async def test_fully_assigned_tba_is_zero(self):
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("1000.00"))
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("0")

    async def test_over_assigned_tba_is_negative(self):
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("1500.00"))
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("-500.00")

    async def test_multiple_categories_combined_reduce_tba(self):
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat1 = MockCategory(category_group_id=grp.id)
        cat2 = MockCategory(category_group_id=grp.id)
        cat3 = MockCategory(category_group_id=grp.id)
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[cat1, cat2, cat3],
            groups=[grp],
            assignments_by_category={
                cat1.id: [MockAssignment(category_id=cat1.id, month=JAN, assigned=D("300.00"))],
                cat2.id: [MockAssignment(category_id=cat2.id, month=JAN, assigned=D("200.00"))],
                cat3.id: [MockAssignment(category_id=cat3.id, month=JAN, assigned=D("100.00"))],
            },
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("400.00")

    async def test_unassigned_category_does_not_reduce_tba(self):
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        # No assignments at all — category available = 0
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[cat],
            groups=[grp],
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("1000.00")

    async def test_spent_against_assigned_reduces_available_and_affects_tba(self):
        """Spending reduces both account balance and category available by the same amount,
        so TBA stays constant.
        """
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        assign = MockAssignment(category_id=cat.id, month=JAN, assigned=D("500.00"))
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("800.00")},  # $1000 minus $200 spent
            categories=[cat],
            groups=[grp],
            assignments_by_category={cat.id: [assign]},
            activity_by_category={cat.id: {JAN: D("-200.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # account: 800, category available: 500-200=300, TBA: 800-300=500
        assert result.to_be_assigned == D("500.00")


class TestTBASystemCategoryExclusion:
    async def test_system_income_group_excluded(self):
        """Income group (is_system=True) categories do NOT reduce TBA."""
        acct = MockAccount()
        income_grp = MockCategoryGroup(name="Income", is_system=True)
        income_cat = MockCategory(category_group_id=income_grp.id)
        assign = MockAssignment(category_id=income_cat.id, month=JAN, assigned=D("3000.00"))
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("3000.00")},
            categories=[income_cat],
            groups=[income_grp],
            assignments_by_category={income_cat.id: [assign]},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("3000.00")

    async def test_mixed_system_and_regular_groups(self):
        """Only regular group categories reduce TBA; system group categories do not."""
        acct = MockAccount()
        income_grp = MockCategoryGroup(name="Income", is_system=True)
        expense_grp = MockCategoryGroup(name="Food", is_system=False)
        income_cat = MockCategory(category_group_id=income_grp.id)
        expense_cat = MockCategory(category_group_id=expense_grp.id)
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("3000.00")},
            categories=[income_cat, expense_cat],
            groups=[income_grp, expense_grp],
            assignments_by_category={
                income_cat.id: [
                    MockAssignment(category_id=income_cat.id, month=JAN, assigned=D("3000.00"))
                ],
                expense_cat.id: [
                    MockAssignment(category_id=expense_cat.id, month=JAN, assigned=D("400.00"))
                ],
            },
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # Only expense_cat (available=400) reduces TBA; income_cat excluded
        assert result.to_be_assigned == D("2600.00")

    async def test_income_not_system_flag_incorrectly_reduces_tba(self):
        """
        Documents the data integrity bug: if 'Income' group lacks is_system=True (as happened
        with YNAB imports before migration c3d4e5f6a7b8), income activity reduces TBA incorrectly.

        With correct is_system=True: TBA = account_balance (income excluded)
        With incorrect is_system=False: TBA = account_balance - income_available (wrong)
        """
        acct = MockAccount()
        misconfigured_income_grp = MockCategoryGroup(name="Income", is_system=False)
        income_cat = MockCategory(category_group_id=misconfigured_income_grp.id)
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("3000.00")},
            categories=[income_cat],
            groups=[misconfigured_income_grp],
            activity_by_category={income_cat.id: {JAN: D("3000.00")}},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # Bug: income activity (3000) incorrectly reduces TBA → TBA = 3000 - 3000 = 0
        assert result.to_be_assigned == D("0")  # should be D("3000.00") with correct flag

    async def test_multiple_system_groups_all_excluded(self):
        """All system groups are excluded from TBA, not just the first one found."""
        acct = MockAccount()
        sys_grp1 = MockCategoryGroup(is_system=True)
        sys_grp2 = MockCategoryGroup(is_system=True)
        reg_grp = MockCategoryGroup(is_system=False)
        sys_cat1 = MockCategory(category_group_id=sys_grp1.id)
        sys_cat2 = MockCategory(category_group_id=sys_grp2.id)
        reg_cat = MockCategory(category_group_id=reg_grp.id)
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[sys_cat1, sys_cat2, reg_cat],
            groups=[sys_grp1, sys_grp2, reg_grp],
            assignments_by_category={
                sys_cat1.id: [
                    MockAssignment(category_id=sys_cat1.id, month=JAN, assigned=D("500.00"))
                ],
                sys_cat2.id: [
                    MockAssignment(category_id=sys_cat2.id, month=JAN, assigned=D("300.00"))
                ],
                reg_cat.id: [
                    MockAssignment(category_id=reg_cat.id, month=JAN, assigned=D("200.00"))
                ],
            },
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        # Only reg_cat (200) reduces TBA
        assert result.to_be_assigned == D("800.00")


class TestTBAAccountFiltering:
    async def test_off_budget_account_excluded(self):
        on_budget = MockAccount(on_budget=True)
        off_budget = MockAccount(on_budget=False)
        svc = make_service(
            accounts=[on_budget, off_budget],
            balances={on_budget.id: D("1000.00"), off_budget.id: D("5000.00")},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("1000.00")

    async def test_closed_account_still_funds_tba(self):
        """Closing an account moves no money: its transactions stay and its
        categorized history stays in the envelopes, so leaving its balance
        out changed Ready to Assign by exactly that balance with nothing to
        show for it."""
        active = MockAccount(is_closed=False)
        closed = MockAccount(is_closed=True)
        svc = make_service(
            accounts=[active, closed],
            balances={active.id: D("800.00"), closed.id: D("2000.00")},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("2800.00")

    async def test_off_budget_out_closed_in(self):
        active = MockAccount(on_budget=True, is_closed=False)
        off_budget = MockAccount(on_budget=False, is_closed=False)
        closed = MockAccount(on_budget=True, is_closed=True)
        svc = make_service(
            accounts=[active, off_budget, closed],
            balances={active.id: D("500.00"), off_budget.id: D("1000.00"), closed.id: D("2000.00")},
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("2500.00")

    async def test_zero_balance_account_is_neutral(self):
        acct = MockAccount()
        svc = make_service(accounts=[acct], balances={acct.id: D("0")})
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("0")


class TestTBASummaryTotals:
    async def test_total_assigned_sums_current_month_only(self):
        """total_assigned reflects each category's assignment for the queried month."""
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat1 = MockCategory(category_group_id=grp.id)
        cat2 = MockCategory(category_group_id=grp.id)
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[cat1, cat2],
            groups=[grp],
            assignments_by_category={
                cat1.id: [MockAssignment(category_id=cat1.id, month=JAN, assigned=D("300.00"))],
                cat2.id: [MockAssignment(category_id=cat2.id, month=JAN, assigned=D("200.00"))],
            },
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.total_assigned == D("500.00")

    async def test_total_activity_sums_current_month_only(self):
        """total_activity reflects each category's spend/income for the queried month."""
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat1 = MockCategory(category_group_id=grp.id)
        cat2 = MockCategory(category_group_id=grp.id)
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[cat1, cat2],
            groups=[grp],
            activity_by_category={
                cat1.id: {JAN: D("-45.00")},
                cat2.id: {JAN: D("-30.00")},
            },
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.total_activity == D("-75.00")

    async def test_category_balances_list_has_entry_per_category(self):
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat1 = MockCategory(category_group_id=grp.id)
        cat2 = MockCategory(category_group_id=grp.id)
        cat3 = MockCategory(category_group_id=grp.id)
        svc = make_service(
            accounts=[acct],
            balances={acct.id: D("1000.00")},
            categories=[cat1, cat2, cat3],
            groups=[grp],
        )
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert len(result.category_balances) == 3


class TestTBAFutureAssignments:
    """Assigning ahead must reduce the earlier months' TBA (YNAB behavior):
    without the deduction the same dollars could be assigned twice."""

    def _one_cat_service(self, balance, assignments):
        acct = MockAccount()
        grp = MockCategoryGroup()
        cat = MockCategory(category_group_id=grp.id)
        svc = make_service(
            accounts=[acct],
            balances={acct.id: balance},
            categories=[cat],
            groups=[grp],
            assignments_by_category={
                cat.id: [
                    MockAssignment(category_id=cat.id, month=m, assigned=amt)
                    for m, amt in assignments
                ]
            },
        )
        return svc

    async def test_future_assignment_reduces_current_tba(self):
        svc = self._one_cat_service(D("1000.00"), [(FEB, D("500.00"))])
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("500.00")
        assert result.assigned_in_future == D("500.00")

    async def test_tba_consistent_between_viewed_months(self):
        """The same $500 shows the same TBA from January (as a future
        commitment) and from February (as a category balance)."""
        svc = self._one_cat_service(D("1000.00"), [(FEB, D("500.00"))])
        jan = await svc.get_budget_summary(BUDGET_ID, JAN)
        feb = await svc.get_budget_summary(BUDGET_ID, FEB)
        assert jan.to_be_assigned == feb.to_be_assigned == D("500.00")
        assert feb.assigned_in_future == D("0")

    async def test_multiple_future_months_all_deducted(self):
        mar = date(2026, 3, 1)
        svc = self._one_cat_service(D("1000.00"), [(FEB, D("200.00")), (mar, D("300.00"))])
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.assigned_in_future == D("500.00")
        assert result.to_be_assigned == D("500.00")

    async def test_current_and_future_assignments_not_double_counted(self):
        """JAN's own assignment lands in category balances; only FEB's is a
        future commitment. 1000 - 400 - 100 = 500 from either month."""
        svc = self._one_cat_service(D("1000.00"), [(JAN, D("400.00")), (FEB, D("100.00"))])
        jan = await svc.get_budget_summary(BUDGET_ID, JAN)
        feb = await svc.get_budget_summary(BUDGET_ID, FEB)
        assert jan.to_be_assigned == D("500.00")
        assert jan.assigned_in_future == D("100.00")
        assert feb.to_be_assigned == D("500.00")

    async def test_assigning_ahead_beyond_funds_pushes_tba_negative(self):
        """Committing more to the future than exists on hand must show as
        negative TBA now, not silently on arrival in that month."""
        svc = self._one_cat_service(D("100.00"), [(FEB, D("500.00"))])
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.to_be_assigned == D("-400.00")

    async def test_no_future_assignments_field_is_zero(self):
        svc = self._one_cat_service(D("1000.00"), [(JAN, D("400.00"))])
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.assigned_in_future == D("0")
        assert result.to_be_assigned == D("600.00")

    async def test_negative_future_assignment_returns_money_to_tba(self):
        """A negative assignment in a future month (money pulled back out)
        increases current TBA symmetrically."""
        svc = self._one_cat_service(D("1000.00"), [(JAN, D("400.00")), (FEB, D("-100.00"))])
        result = await svc.get_budget_summary(BUDGET_ID, JAN)
        assert result.assigned_in_future == D("-100.00")
        assert result.to_be_assigned == D("700.00")
