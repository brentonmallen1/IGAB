"""
Category balance and YNAB floor simulation tests for BudgetService.get_category_balance.

YNAB floor simulation rules:
  - Each month: end_of_month = carryover + assigned + activity
  - Between months: carryover = max(0, end_of_month)  ← floor negative at 0
  - Current month available = end_of_month  ← can still show negative in current month

When a category is cash-overspent (end < 0), the negative is floored to 0 for the
NEXT month, meaning TBA absorbs the overspend and the category starts fresh at 0.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from igab.services.budget_service import BudgetService

JAN = date(2026, 1, 1)
FEB = date(2026, 2, 1)
MAR = date(2026, 3, 1)
APR = date(2026, 4, 1)


def D(s: str) -> Decimal:
    return Decimal(s)


@dataclass
class MockAssignment:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    category_id: uuid.UUID = field(default_factory=uuid.uuid4)
    month: date = JAN
    assigned: Decimal = D("0")


def make_service(assignments: list[MockAssignment]) -> BudgetService:
    """Minimal BudgetService for testing get_category_balance in isolation."""
    assignment_repo = MagicMock()
    assignment_repo.get_for_category = AsyncMock(return_value=assignments)
    return BudgetService(
        account_repo=MagicMock(),
        category_repo=MagicMock(),
        category_group_repo=MagicMock(),
        assignment_repo=assignment_repo,
        transaction_repo=MagicMock(),
    )


CAT_ID = uuid.uuid4()


class TestSingleMonthBalance:
    async def test_no_data_returns_zero(self):
        svc = make_service([])
        bal = await svc.get_category_balance(CAT_ID, JAN, activity_by_month={})
        assert bal.available == D("0")
        assert bal.assigned == D("0")
        assert bal.activity == D("0")

    async def test_assigned_only(self):
        assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        svc = make_service([assign])
        bal = await svc.get_category_balance(CAT_ID, JAN, activity_by_month={})
        assert bal.available == D("100.00")
        assert bal.assigned == D("100.00")
        assert bal.activity == D("0")

    async def test_assigned_with_partial_spend(self):
        assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        svc = make_service([assign])
        bal = await svc.get_category_balance(CAT_ID, JAN, activity_by_month={JAN: D("-45.00")})
        assert bal.available == D("55.00")
        assert bal.assigned == D("100.00")
        assert bal.activity == D("-45.00")

    async def test_assigned_fully_spent(self):
        assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        svc = make_service([assign])
        bal = await svc.get_category_balance(CAT_ID, JAN, activity_by_month={JAN: D("-100.00")})
        assert bal.available == D("0")

    async def test_overspent_shows_negative_available(self):
        assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        svc = make_service([assign])
        bal = await svc.get_category_balance(CAT_ID, JAN, activity_by_month={JAN: D("-150.00")})
        assert bal.available == D("-50.00")

    async def test_activity_only_no_assignment(self):
        """Activity with no assignment shows negative available."""
        svc = make_service([])
        bal = await svc.get_category_balance(CAT_ID, JAN, activity_by_month={JAN: D("-75.00")})
        assert bal.available == D("-75.00")
        assert bal.assigned == D("0")

    async def test_income_activity_positive_available(self):
        """Categories can have positive activity (e.g., income or refunds)."""
        svc = make_service([])
        bal = await svc.get_category_balance(CAT_ID, JAN, activity_by_month={JAN: D("200.00")})
        assert bal.available == D("200.00")


class TestPositiveCarryover:
    async def test_surplus_carries_to_next_month(self):
        """$100 assigned in Jan with no spend → $100 available in Feb."""
        jan_assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        svc = make_service([jan_assign])
        bal = await svc.get_category_balance(
            CAT_ID, FEB, activity_by_month={JAN: D("0")}
        )
        assert bal.available == D("100.00")

    async def test_surplus_plus_new_assignment(self):
        """$60 carryover from Jan + $40 assigned in Feb → $100 available."""
        jan_assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        feb_assign = MockAssignment(category_id=CAT_ID, month=FEB, assigned=D("40.00"))
        svc = make_service([jan_assign, feb_assign])
        bal = await svc.get_category_balance(
            CAT_ID, FEB, activity_by_month={JAN: D("-60.00")}
        )
        # Jan: 0+100-60=40, carryover=40; Feb: 40+40+0=80
        assert bal.available == D("80.00")

    async def test_surplus_carries_across_multiple_months(self):
        """$200 assigned in Jan with no spend carries through Feb and Mar."""
        jan_assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("200.00"))
        svc = make_service([jan_assign])
        bal = await svc.get_category_balance(CAT_ID, MAR, activity_by_month={})
        assert bal.available == D("200.00")

    async def test_two_month_positive_progression(self):
        """Jan: $100/-$60=40 carryover; Feb: $0/-$20 → available=20."""
        jan_assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        svc = make_service([jan_assign])
        bal = await svc.get_category_balance(
            CAT_ID, FEB, activity_by_month={JAN: D("-60.00"), FEB: D("-20.00")}
        )
        # Jan: 0+100-60=40, carryover=40; Feb: 40+0-20=20
        assert bal.available == D("20.00")


class TestFloorSimulation:
    async def test_overspend_floors_carryover_to_zero(self):
        """
        Jan: $100 assigned, -$150 spent → end=-$50, carryover=0 (floored).
        Feb: $50 assigned → end=0+50=50 (NOT -50+50=0).
        """
        jan_assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        feb_assign = MockAssignment(category_id=CAT_ID, month=FEB, assigned=D("50.00"))
        svc = make_service([jan_assign, feb_assign])
        bal = await svc.get_category_balance(
            CAT_ID, FEB, activity_by_month={JAN: D("-150.00")}
        )
        # Jan: 0+100-150=-50, carryover=max(0,-50)=0
        # Feb: 0+50+0=50
        assert bal.available == D("50.00")

    async def test_floor_does_not_apply_within_current_month(self):
        """The floor only applies between months. Current month CAN show negative."""
        assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        svc = make_service([assign])
        bal = await svc.get_category_balance(
            CAT_ID, JAN, activity_by_month={JAN: D("-150.00")}
        )
        assert bal.available == D("-50.00")  # negative is allowed in current month

    async def test_three_month_floor_scenario(self):
        """
        Canonical three-month floor scenario from the plan:
          Jan: $100 assigned, -$150 spent → end=-$50, carryover=0
          Feb: $50 assigned, $0 spent   → end=$50, carryover=$50
          Mar: $0 assigned, -$30 spent  → end=$20

        Querying March should show available=$20.
        """
        jan_assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        feb_assign = MockAssignment(category_id=CAT_ID, month=FEB, assigned=D("50.00"))
        svc = make_service([jan_assign, feb_assign])
        bal = await svc.get_category_balance(
            CAT_ID, MAR,
            activity_by_month={JAN: D("-150.00"), MAR: D("-30.00")},
        )
        assert bal.available == D("20.00")

    async def test_successive_overspends_each_floored(self):
        """Each month's overspend floors independently; they do not compound."""
        jan_assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        feb_assign = MockAssignment(category_id=CAT_ID, month=FEB, assigned=D("100.00"))
        mar_assign = MockAssignment(category_id=CAT_ID, month=MAR, assigned=D("100.00"))
        svc = make_service([jan_assign, feb_assign, mar_assign])
        bal = await svc.get_category_balance(
            CAT_ID, MAR,
            activity_by_month={JAN: D("-150.00"), FEB: D("-150.00"), MAR: D("-150.00")},
        )
        # Jan: end=-50, carryover=0
        # Feb: end=0+100-150=-50, carryover=0
        # Mar: end=0+100-150=-50 → available=-50
        assert bal.available == D("-50.00")

    async def test_zero_overspend_boundary(self):
        """Exactly zero at end of month: carryover=0, next month starts at 0."""
        jan_assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        feb_assign = MockAssignment(category_id=CAT_ID, month=FEB, assigned=D("50.00"))
        svc = make_service([jan_assign, feb_assign])
        bal = await svc.get_category_balance(
            CAT_ID, FEB, activity_by_month={JAN: D("-100.00")}
        )
        # Jan: end=0, carryover=0; Feb: end=0+50=50
        assert bal.available == D("50.00")

    async def test_four_month_mixed_scenario(self):
        """Complex multi-month scenario verifying floor at each step."""
        assigns = [
            MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("200.00")),
            MockAssignment(category_id=CAT_ID, month=FEB, assigned=D("0.00")),
            MockAssignment(category_id=CAT_ID, month=MAR, assigned=D("100.00")),
            MockAssignment(category_id=CAT_ID, month=APR, assigned=D("50.00")),
        ]
        svc = make_service(assigns)
        bal = await svc.get_category_balance(
            CAT_ID, APR,
            activity_by_month={
                JAN: D("-250.00"),  # overspend: end=-50, carryover=0
                FEB: D("-30.00"),   # end=0+0-30=-30, carryover=0
                MAR: D("-60.00"),   # end=0+100-60=40, carryover=40
                APR: D("-20.00"),   # end=40+50-20=70
            },
        )
        assert bal.available == D("70.00")


class TestActivityBeforeAssignment:
    async def test_activity_in_month_before_first_assignment(self):
        """
        Activity in a month with no assignment floors to 0 before the first assignment month.
        Jan: $0 assigned, -$50 spent → end=-50, carryover=0
        Feb: $100 assigned → end=0+100=100
        """
        feb_assign = MockAssignment(category_id=CAT_ID, month=FEB, assigned=D("100.00"))
        svc = make_service([feb_assign])
        bal = await svc.get_category_balance(
            CAT_ID, FEB, activity_by_month={JAN: D("-50.00")}
        )
        # Jan: 0+0-50=-50, carryover=0; Feb: 0+100+0=100
        assert bal.available == D("100.00")

    async def test_activity_only_with_no_assignments_ever(self):
        """Category with spend but no assignments ever — available tracks cumulative spend."""
        svc = make_service([])
        bal = await svc.get_category_balance(
            CAT_ID, MAR,
            activity_by_month={JAN: D("-50.00"), FEB: D("-30.00"), MAR: D("-20.00")},
        )
        # Jan: end=-50, carryover=0; Feb: end=0-30=-30, carryover=0; Mar: end=0-20=-20
        assert bal.available == D("-20.00")


class TestQueryMonthBoundary:
    async def test_query_first_month_only_processes_that_month(self):
        """Querying Jan should not include Feb data even if Feb assignments exist."""
        jan_assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        feb_assign = MockAssignment(category_id=CAT_ID, month=FEB, assigned=D("200.00"))
        svc = make_service([jan_assign, feb_assign])
        bal = await svc.get_category_balance(
            CAT_ID, JAN, activity_by_month={JAN: D("-30.00"), FEB: D("-50.00")}
        )
        # Only Jan processed (m > month_start breaks)
        assert bal.available == D("70.00")
        assert bal.assigned == D("100.00")
        assert bal.activity == D("-30.00")

    async def test_query_middle_of_sequence(self):
        """Querying Feb of a Jan-Feb-Mar sequence stops at Feb."""
        jan_assign = MockAssignment(category_id=CAT_ID, month=JAN, assigned=D("100.00"))
        feb_assign = MockAssignment(category_id=CAT_ID, month=FEB, assigned=D("50.00"))
        mar_assign = MockAssignment(category_id=CAT_ID, month=MAR, assigned=D("50.00"))
        svc = make_service([jan_assign, feb_assign, mar_assign])
        bal = await svc.get_category_balance(
            CAT_ID, FEB,
            activity_by_month={JAN: D("-150.00"), FEB: D("-10.00"), MAR: D("-20.00")},
        )
        # Jan: 0+100-150=-50, carryover=0; Feb: 0+50-10=40
        assert bal.available == D("40.00")
        assert bal.assigned == D("50.00")
        assert bal.activity == D("-10.00")

    async def test_returns_correct_month_on_balance_object(self):
        svc = make_service([])
        bal = await svc.get_category_balance(CAT_ID, FEB, activity_by_month={})
        assert bal.month == FEB
        assert bal.category_id == CAT_ID
