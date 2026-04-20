from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from igab.services.target_service import TargetService, _months_between


def make_target(target_type: str, amount: str, target_date: date | None = None) -> MagicMock:
    t = MagicMock()
    t.target_type = target_type
    t.target_amount = Decimal(amount)
    t.target_date = target_date
    return t


class TestMonthsBetween:
    def test_same_month(self):
        assert _months_between(date(2024, 3, 1), date(2024, 3, 31)) >= 1

    def test_one_month(self):
        assert _months_between(date(2024, 3, 1), date(2024, 4, 1)) == 1

    def test_twelve_months(self):
        assert _months_between(date(2024, 1, 1), date(2025, 1, 1)) == 12

    def test_cross_year(self):
        assert _months_between(date(2024, 11, 1), date(2025, 2, 1)) == 3

    def test_minimum_is_one(self):
        # Past or same date should return at least 1
        assert _months_between(date(2024, 5, 1), date(2024, 3, 1)) >= 1


class TestCalculateStatus:
    def setup_method(self):
        self.svc = TargetService(MagicMock())

    def test_monthly_funding_funded(self):
        target = make_target("monthly_funding", "500")
        assert self.svc.calculate_status(target, Decimal("500"), Decimal("500")) == "funded"

    def test_monthly_funding_underfunded(self):
        target = make_target("monthly_funding", "500")
        assert self.svc.calculate_status(target, Decimal("400"), Decimal("400")) == "underfunded"

    def test_monthly_funding_overfunded(self):
        target = make_target("monthly_funding", "500")
        # Over 5% threshold → overfunded
        assert self.svc.calculate_status(target, Decimal("600"), Decimal("600")) == "overfunded"

    def test_monthly_funding_just_at_threshold(self):
        # Exactly 5% over = funded (not overfunded)
        target = make_target("monthly_funding", "500")
        assert self.svc.calculate_status(target, Decimal("525"), Decimal("525")) == "funded"

    def test_savings_balance_funded(self):
        # available already meets target
        target = make_target("savings_balance", "1000")
        assert self.svc.calculate_status(target, Decimal("0"), Decimal("1000")) == "funded"

    def test_savings_balance_underfunded(self):
        target = make_target("savings_balance", "1000")
        assert self.svc.calculate_status(target, Decimal("0"), Decimal("500")) == "underfunded"

    def test_savings_balance_assigned_covers_shortfall(self):
        # available=600, target=1000, shortfall=400, assigned=400 → funded
        target = make_target("savings_balance", "1000")
        assert self.svc.calculate_status(target, Decimal("400"), Decimal("600")) == "funded"

    def test_needed_for_spending_no_date_uses_full_amount(self):
        target = make_target("needed_for_spending", "300", target_date=None)
        assert self.svc.calculate_status(target, Decimal("300"), Decimal("0")) == "funded"

    def test_weekly_funding_funded(self):
        target = make_target("weekly_funding", "100")
        assert self.svc.calculate_status(target, Decimal("100"), Decimal("100")) == "funded"

    def test_weekly_funding_underfunded(self):
        target = make_target("weekly_funding", "100")
        assert self.svc.calculate_status(target, Decimal("50"), Decimal("50")) == "underfunded"
