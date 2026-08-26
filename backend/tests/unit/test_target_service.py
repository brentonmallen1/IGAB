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

    def test_savings_balance_is_judged_on_the_balance_not_the_assignment(self):
        # available=600 against a 1000 goal, 400 assigned this month. This read
        # "funded" until the pill was tied to Fill Underfunded: 400 of what was
        # assigned had been spent again, the balance is still 400 short, and
        # Fill Underfunded moves 400 more. A pill that says funded there is
        # predicting the opposite of what the button does.
        target = make_target("savings_balance", "1000")
        assert self.svc.calculate_status(target, Decimal("400"), Decimal("600")) == "underfunded"

    def test_savings_balance_funded_once_the_balance_arrives(self):
        target = make_target("savings_balance", "1000")
        assert self.svc.calculate_status(target, Decimal("400"), Decimal("1000")) == "funded"

    def test_savings_balance_overfunded_reads_the_balance_too(self):
        target = make_target("savings_balance", "1000")
        assert self.svc.calculate_status(target, Decimal("0"), Decimal("1100")) == "overfunded"

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

    @pytest.mark.parametrize(
        ("assigned", "available"),
        [("0", "0"), ("400", "600"), ("0", "1000"), ("400", "1000"), ("0", "1100")],
    )
    def test_savings_balance_agrees(self, assigned, available):
        target = make_target("savings_balance", "1000")
        status = self.svc.calculate_status(target, Decimal(assigned), Decimal(available))
        needed = self.svc.calculate_needed(target, Decimal(assigned), Decimal(available))
        assert (status == "underfunded") == (needed > 0)


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


class TestMonthlyPace:
    """The pace a wish can count on — see TargetService.monthly_pace."""

    def setup_method(self):
        self.svc = TargetService(repo=MagicMock())
        self.today = date(2026, 8, 26)

    def test_monthly_and_weekly_are_their_amount(self):
        assert self.svc.monthly_pace(make_target("monthly_funding", "100"), Decimal("0"), self.today) == Decimal("100")
        assert self.svc.monthly_pace(make_target("weekly_funding", "25"), Decimal("0"), self.today) == Decimal("25")

    def test_dated_needed_for_spending_matches_needed_gross(self):
        t = make_target("needed_for_spending", "600", date(2027, 2, 1))
        available = Decimal("0")
        assert self.svc.monthly_pace(t, available, self.today) == self.svc.needed_gross(
            t, available, self.today
        )

    def test_a_dated_savings_goal_paces_by_its_date_although_fill_underfunded_fills_it_whole(self):
        t = make_target("savings_balance", "1200", date(2027, 2, 1))  # six months away
        pace = self.svc.monthly_pace(t, Decimal("0"), self.today)
        assert pace == Decimal("200")
        # The divergence, named: Fill Underfunded asks for the lot now.
        assert self.svc.needed_gross(t, Decimal("0"), self.today) == Decimal("1200")

    def test_an_undated_savings_goal_has_no_pace(self):
        assert self.svc.monthly_pace(make_target("savings_balance", "1200"), Decimal("0"), self.today) is None

    def test_a_past_due_savings_goal_is_the_whole_shortfall(self):
        t = make_target("savings_balance", "1200", date(2026, 1, 1))
        assert self.svc.monthly_pace(t, Decimal("200"), self.today) == Decimal("1000")
