"""
Tests for TargetService.calculate_needed().

calculate_needed() returns the amount still needed this month to reach
the target. It must always be >= 0 (you cannot "need" negative funds).

Target types:
  - monthly_funding: need target_amount - assigned (floor 0)
  - weekly_funding: need amount × weekday occurrences - assigned (floor 0)
  - savings_balance (no date): need target_amount - available (floor 0)
  - savings_balance (with date): the month's pace minus already assigned

All arithmetic rules in this function directly affect how much money gets
assigned to categories via auto-assign. Bugs here mean wrong amounts.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from igab.services.target_service import TargetService

MAY = date(2026, 5, 1)  # five Fridays
FRIDAY = 4


def D(s: str) -> Decimal:
    return Decimal(s)


def make_target(
    target_type: str, amount: str, target_date: date | None = None, *, weekday: int | None = None
) -> MagicMock:
    t = MagicMock()
    t.target_type = target_type
    t.target_amount = D(amount)
    t.target_date = target_date
    t.weekday = weekday
    t.check_after_day = None
    return t


@pytest.fixture
def svc() -> TargetService:
    return TargetService(MagicMock())


def needed(svc, target, assigned, available, month=MAY):
    return svc.calculate_needed(target, D(assigned), D(available), month=month)


class TestMonthlyFundingNeeded:
    def test_fully_assigned_returns_zero(self, svc):
        assert needed(svc, make_target("monthly_funding", "500"), "500", "500") == D("0")

    def test_nothing_assigned_returns_full_target(self, svc):
        assert needed(svc, make_target("monthly_funding", "500"), "0", "0") == D("500")

    def test_partial_assignment_returns_shortfall(self, svc):
        assert needed(svc, make_target("monthly_funding", "500"), "300", "300") == D("200")

    def test_overfunded_returns_zero_not_negative(self, svc):
        assert needed(svc, make_target("monthly_funding", "500"), "700", "700") == D("0")

    def test_exactly_one_cent_short(self, svc):
        assert needed(svc, make_target("monthly_funding", "500"), "499.99", "499.99") == D("0.01")

    def test_large_target(self, svc):
        t = make_target("monthly_funding", "1000000")
        assert needed(svc, t, "999999", "999999") == D("1")


class TestSavingsBalanceNeeded:
    def test_available_meets_target_returns_zero(self, svc):
        assert needed(svc, make_target("savings_balance", "1000"), "0", "1000") == D("0")

    def test_available_exceeds_target_returns_zero(self, svc):
        assert needed(svc, make_target("savings_balance", "1000"), "0", "1500") == D("0")

    def test_nothing_saved_returns_full_target(self, svc):
        assert needed(svc, make_target("savings_balance", "1000"), "0", "0") == D("1000")

    def test_partial_available_returns_shortfall(self, svc):
        assert needed(svc, make_target("savings_balance", "1000"), "0", "600") == D("400")

    def test_available_is_negative_returns_full_target_plus_deficit(self, svc):
        assert needed(svc, make_target("savings_balance", "1000"), "0", "-200") == D("1200")

    def test_savings_balance_with_assignment_doesnt_affect_calculation(self, svc):
        # `available` already contains this month's assignment; subtracting
        # `assigned` again would ask for the money twice.
        assert needed(svc, make_target("savings_balance", "1000"), "400", "600") == D("400")


class TestDatedSavingsNeeded:
    def test_single_month_remaining_returns_full_remaining(self, svc):
        t = make_target("savings_balance", "600", date(2026, 5, 20))
        assert needed(svc, t, "0", "100") == D("500")

    def test_six_months_remaining_splits_evenly(self, svc):
        t = make_target("savings_balance", "600", date(2026, 11, 1))
        assert needed(svc, t, "0", "0") == D("100")

    def test_already_assigned_this_month_reduces_needed(self, svc):
        t = make_target("savings_balance", "600", date(2026, 11, 1))
        assert needed(svc, t, "40", "40") == D("60")

    def test_fully_funded_returns_zero(self, svc):
        t = make_target("savings_balance", "600", date(2026, 11, 1))
        assert needed(svc, t, "100", "100") == D("0")

    def test_overfunded_returns_zero(self, svc):
        t = make_target("savings_balance", "600", date(2026, 11, 1))
        assert needed(svc, t, "150", "150") == D("0")

    def test_balance_already_reached_returns_zero(self, svc):
        t = make_target("savings_balance", "600", date(2026, 11, 1))
        assert needed(svc, t, "0", "700") == D("0")


class TestWeeklyFundingNeeded:
    def test_nothing_assigned(self, svc):
        t = make_target("weekly_funding", "50", weekday=FRIDAY)
        assert needed(svc, t, "0", "0") == D("250")

    def test_fully_assigned(self, svc):
        t = make_target("weekly_funding", "50", weekday=FRIDAY)
        assert needed(svc, t, "250", "250") == D("0")

    def test_partial_assignment(self, svc):
        t = make_target("weekly_funding", "50", weekday=FRIDAY)
        assert needed(svc, t, "100", "100") == D("150")

    def test_overfunded_returns_zero(self, svc):
        t = make_target("weekly_funding", "50", weekday=FRIDAY)
        assert needed(svc, t, "300", "300") == D("0")

    def test_a_four_week_month_asks_for_four(self, svc):
        t = make_target("weekly_funding", "50", weekday=FRIDAY)
        assert needed(svc, t, "0", "0", month=date(2026, 6, 1)) == D("200")


class TestNeededNeverNegative:
    @pytest.mark.parametrize(
        "target",
        [
            make_target("monthly_funding", "100"),
            make_target("weekly_funding", "100", weekday=0),
            make_target("savings_balance", "100"),
            make_target("savings_balance", "100", date(2026, 11, 1)),
        ],
        ids=["monthly", "weekly", "savings", "dated-savings"],
    )
    def test_always_non_negative_for_overfunded(self, svc, target):
        assert needed(svc, target, "10000", "10000") >= D("0")

    @pytest.mark.parametrize(
        "target",
        [
            make_target("monthly_funding", "0"),
            make_target("weekly_funding", "0", weekday=0),
            make_target("savings_balance", "0"),
        ],
        ids=["monthly", "weekly", "savings"],
    )
    def test_zero_target_amount_returns_zero(self, svc, target):
        assert needed(svc, target, "0", "0") == D("0")
