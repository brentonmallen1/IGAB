from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from igab.domain.dates import months_between
from igab.services.target_service import TargetService


def make_target(target_type: str, amount: str, target_date: date | None = None) -> MagicMock:
    t = MagicMock()
    t.target_type = target_type
    t.target_amount = Decimal(amount)
    t.target_date = target_date
    return t


class TestMonthsBetween:
    def test_same_month(self):
        assert months_between(date(2024, 3, 1), date(2024, 3, 31)) >= 1

    def test_one_month(self):
        assert months_between(date(2024, 3, 1), date(2024, 4, 1)) == 1

    def test_twelve_months(self):
        assert months_between(date(2024, 1, 1), date(2025, 1, 1)) == 12

    def test_cross_year(self):
        assert months_between(date(2024, 11, 1), date(2025, 2, 1)) == 3

    def test_minimum_is_one(self):
        # Past or same date should return at least 1
        assert months_between(date(2024, 5, 1), date(2024, 3, 1)) >= 1


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


class TestThePillPredictsFillUnderfunded:
    """The budget row's pill exists to say what Fill Underfunded will do.

    Both now derive from `needed_gross`, so they cannot disagree about the
    duty. The invariant that follows: "underfunded" and "there is still
    something to assign" are the same statement.
    """

    svc = TargetService(repo=None)  # type: ignore[arg-type]

    @pytest.mark.parametrize("target_type", ["monthly_funding", "weekly_funding"])
    @pytest.mark.parametrize(
        ("assigned", "available"),
        [("0", "0"), ("50", "50"), ("100", "100"), ("150", "150"), ("0", "500")],
    )
    def test_funding_targets_agree(self, target_type, assigned, available):
        target = make_target(target_type, "100")
        status = self.svc.calculate_status(target, Decimal(assigned), Decimal(available))
        needed = self.svc.calculate_needed(target, Decimal(assigned), Decimal(available))
        assert (status == "underfunded") == (needed > 0)

    @pytest.mark.parametrize(
        ("assigned", "available"),
        [("0", "0"), ("300", "300"), ("0", "600"), ("300", "600"), ("0", "700")],
    )
    def test_dated_needed_for_spending_agrees(self, assigned, available):
        target = make_target("needed_for_spending", "600", target_date=date(2026, 6, 1))
        with patch("igab.services.target_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)
            status = self.svc.calculate_status(target, Decimal(assigned), Decimal(available))
            needed = self.svc.calculate_needed(target, Decimal(assigned), Decimal(available))
        assert (status == "underfunded") == (needed > 0)

    def test_a_savings_balance_goal_can_still_read_funded_while_short(self):
        """KNOWN DIVERGENCE — deliberately pinned, not endorsed.

        available=600 against a 1000 goal, with 400 assigned this month: the
        pill reads "funded" because assigned covers the shortfall, while
        calculate_needed still returns 400 and Fill Underfunded would move it.

        The two are consistent about the *duty* now; what differs is the
        measure the status compares it against — `assigned` for a goal whose
        shortfall is expressed in `available`. Fixing it means deciding that
        a savings-balance target is funded when the BALANCE is met, which
        changes what the pill says on live budgets. Flagged rather than
        changed here; `test_savings_balance_assigned_covers_shortfall` above
        pins the current answer.
        """
        target = make_target("savings_balance", "1000")
        assigned, available = Decimal("400"), Decimal("600")

        assert self.svc.calculate_status(target, assigned, available) == "funded"
        assert self.svc.calculate_needed(target, assigned, available) == Decimal("400")


class TestNeededGrossIsTheOneDuty:
    svc = TargetService(repo=None)  # type: ignore[arg-type]

    def test_both_balance_measured_types_clamp_at_zero(self):
        # The defect this collapse fixed: savings_balance clamped, dated
        # needed_for_spending did not, so an over-target category produced a
        # negative duty in one and zero in the other.
        savings = make_target("savings_balance", "600")
        dated = make_target("needed_for_spending", "600", target_date=date(2026, 6, 1))
        with patch("igab.services.target_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)
            assert self.svc.needed_gross(savings, Decimal("700")) == Decimal("0")
            assert self.svc.needed_gross(dated, Decimal("700")) == Decimal("0")

    def test_measures_balance_names_the_two_shapes(self):
        assert self.svc.measures_balance(make_target("savings_balance", "1"))
        assert self.svc.measures_balance(
            make_target("needed_for_spending", "1", target_date=date(2026, 6, 1))
        )
        assert not self.svc.measures_balance(make_target("monthly_funding", "1"))
        assert not self.svc.measures_balance(make_target("weekly_funding", "1"))
        assert not self.svc.measures_balance(
            make_target("needed_for_spending", "1", target_date=None)
        )

    def test_an_overdue_dated_target_still_asks_once(self):
        target = make_target("needed_for_spending", "600", target_date=date(2025, 1, 1))
        with patch("igab.services.target_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)
            # months_between floors at 1 — the whole shortfall, not a divide by zero.
            assert self.svc.needed_gross(target, Decimal("100")) == Decimal("500")
