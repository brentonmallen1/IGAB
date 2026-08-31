"""
Tests for TargetService.calculate_needed().

calculate_needed() returns the amount still needed this month to reach
the target. It must always be >= 0 (you cannot "need" negative funds).

Target types:
  - monthly_funding: need target_amount - assigned (floor 0)
  - savings_balance: need target_amount - available (floor 0)
  - needed_for_spending (with date): per-month portion minus already assigned
  - needed_for_spending (no date): treat as full target minus assigned
  - weekly_funding: need target_amount - assigned (floor 0)

All arithmetic rules in this function directly affect how much money gets
assigned to categories via auto-assign. Bugs here mean wrong amounts.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from igab.services.target_service import TargetService


def D(s: str) -> Decimal:
    return Decimal(s)


def make_target(target_type: str, amount: str, target_date: date | None = None) -> MagicMock:
    t = MagicMock()
    t.target_type = target_type
    t.target_amount = D(amount)
    t.target_date = target_date
    return t


@pytest.fixture
def svc() -> TargetService:
    return TargetService(MagicMock())


class TestMonthlyFundingNeeded:
    def test_fully_assigned_returns_zero(self, svc):
        target = make_target("monthly_funding", "500")
        assert svc.calculate_needed(target, D("500"), D("500")) == D("0")

    def test_nothing_assigned_returns_full_target(self, svc):
        target = make_target("monthly_funding", "500")
        assert svc.calculate_needed(target, D("0"), D("0")) == D("500")

    def test_partial_assignment_returns_shortfall(self, svc):
        target = make_target("monthly_funding", "500")
        assert svc.calculate_needed(target, D("200"), D("200")) == D("300")

    def test_overfunded_returns_zero_not_negative(self, svc):
        """Overfunding never produces a negative needed amount."""
        target = make_target("monthly_funding", "500")
        assert svc.calculate_needed(target, D("600"), D("600")) == D("0")

    def test_exactly_one_cent_short(self, svc):
        target = make_target("monthly_funding", "500.00")
        assert svc.calculate_needed(target, D("499.99"), D("499.99")) == D("0.01")

    def test_large_target(self, svc):
        target = make_target("monthly_funding", "10000.00")
        assert svc.calculate_needed(target, D("3000.00"), D("3000.00")) == D("7000.00")


class TestSavingsBalanceNeeded:
    def test_available_meets_target_returns_zero(self, svc):
        target = make_target("savings_balance", "1000")
        assert svc.calculate_needed(target, D("0"), D("1000")) == D("0")

    def test_available_exceeds_target_returns_zero(self, svc):
        target = make_target("savings_balance", "1000")
        assert svc.calculate_needed(target, D("0"), D("1200")) == D("0")

    def test_nothing_saved_returns_full_target(self, svc):
        target = make_target("savings_balance", "1000")
        assert svc.calculate_needed(target, D("0"), D("0")) == D("1000")

    def test_partial_available_returns_shortfall(self, svc):
        target = make_target("savings_balance", "1000")
        assert svc.calculate_needed(target, D("0"), D("600")) == D("400")

    def test_available_is_negative_returns_full_target_plus_deficit(self, svc):
        """If available is negative (overspent), more is needed than just the target."""
        target = make_target("savings_balance", "1000")
        # available = -100, shortfall = 1000 - (-100) = 1100
        assert svc.calculate_needed(target, D("0"), D("-100")) == D("1100")

    def test_savings_balance_with_assignment_doesnt_affect_calculation(self, svc):
        """Savings balance is based on available balance, not assigned amount."""
        target = make_target("savings_balance", "1000")
        # assigned=500 but available=300 → still need 700
        assert svc.calculate_needed(target, D("500"), D("300")) == D("700")


class TestNeededForSpendingWithDate:
    def test_single_month_remaining_returns_full_remaining(self, svc):
        target = make_target("needed_for_spending", "300", target_date=date(2026, 5, 1))
        with patch("igab.services.target_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)
            result = svc.calculate_needed(target, D("0"), D("0"))
        assert result == D("300")

    def test_two_months_remaining_splits_evenly(self, svc):
        target = make_target("needed_for_spending", "600", target_date=date(2026, 6, 1))
        with patch("igab.services.target_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)
            # 2 months left, need $300/month. Already assigned 0 this month → need $300
            result = svc.calculate_needed(target, D("0"), D("0"))
        assert result == D("300")

    def test_already_assigned_this_month_reduces_needed(self, svc):
        target = make_target("needed_for_spending", "600", target_date=date(2026, 6, 1))
        with patch("igab.services.target_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)
            # 2 months left, per-month = 300. Already have $200 available.
            # per_month = (600 - 200) / 2 = 200. Already assigned = 100. Need = 100.
            result = svc.calculate_needed(target, D("100"), D("200"))
        assert result == D("100")

    def test_fully_funded_returns_zero(self, svc):
        target = make_target("needed_for_spending", "600", target_date=date(2026, 6, 1))
        with patch("igab.services.target_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)
            # available = 600 = target → needed = 0
            result = svc.calculate_needed(target, D("300"), D("600"))
        assert result == D("0")

    def test_overfunded_returns_zero(self, svc):
        target = make_target("needed_for_spending", "600", target_date=date(2026, 6, 1))
        with patch("igab.services.target_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)
            # available = 700 > target → needed = 0
            result = svc.calculate_needed(target, D("0"), D("700"))
        assert result == D("0")


class TestNeededForSpendingNoDate:
    def test_no_date_uses_full_target_minus_assigned(self, svc):
        target = make_target("needed_for_spending", "300", target_date=None)
        assert svc.calculate_needed(target, D("100"), D("100")) == D("200")

    def test_no_date_fully_funded(self, svc):
        target = make_target("needed_for_spending", "300", target_date=None)
        assert svc.calculate_needed(target, D("300"), D("300")) == D("0")

    def test_no_date_overfunded_returns_zero(self, svc):
        target = make_target("needed_for_spending", "300", target_date=None)
        assert svc.calculate_needed(target, D("400"), D("400")) == D("0")


class TestWeeklyFundingNeeded:
    def test_nothing_assigned(self, svc):
        target = make_target("weekly_funding", "100")
        assert svc.calculate_needed(target, D("0"), D("0")) == D("100")

    def test_fully_assigned(self, svc):
        target = make_target("weekly_funding", "100")
        assert svc.calculate_needed(target, D("100"), D("100")) == D("0")

    def test_partial_assignment(self, svc):
        target = make_target("weekly_funding", "100")
        assert svc.calculate_needed(target, D("60"), D("60")) == D("40")

    def test_overfunded_returns_zero(self, svc):
        target = make_target("weekly_funding", "100")
        assert svc.calculate_needed(target, D("150"), D("150")) == D("0")


class TestNeededNeverNegative:
    """calculate_needed() must always return >= 0 regardless of input."""

    @pytest.mark.parametrize(
        "target_type",
        [
            "monthly_funding",
            "savings_balance",
            "weekly_funding",
        ],
    )
    def test_always_non_negative_for_overfunded(self, svc, target_type):
        target = make_target(target_type, "100")
        result = svc.calculate_needed(target, D("200"), D("200"))
        assert result >= D("0"), f"calculate_needed returned negative for {target_type}"

    @pytest.mark.parametrize(
        "target_type",
        [
            "monthly_funding",
            "weekly_funding",
        ],
    )
    def test_zero_target_amount_returns_zero(self, svc, target_type):
        target = make_target(target_type, "0")
        result = svc.calculate_needed(target, D("0"), D("0"))
        assert result == D("0")
