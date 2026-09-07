"""One duty, three target shapes, and a verdict that predicts Fill Underfunded.

`needed_for_spending` was a fourth shape: undated it computed as monthly
funding, dated as a savings balance with a date. It is gone, and the two
cases it stood for are tested under the names they always had.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from igab.domain.dates import months_between
from igab.domain.exceptions import InvariantViolation
from igab.services.target_service import TargetService

MAY = date(2026, 5, 1)  # five Fridays
JUNE = date(2026, 6, 1)  # four Fridays
FRIDAY = 4


def make_target(
    target_type: str,
    amount: str,
    target_date: date | None = None,
    *,
    weekday: int | None = None,
    check_after_day: int | None = None,
) -> MagicMock:
    t = MagicMock()
    t.target_type = target_type
    t.target_amount = Decimal(amount)
    t.target_date = target_date
    t.weekday = weekday
    t.check_after_day = check_after_day
    return t


def status(svc, target, assigned, available, *, month=MAY, today=None, funding_day=1):
    return svc.calculate_status(
        target,
        Decimal(assigned),
        Decimal(available),
        month=month,
        today=today or month.replace(day=15),
        funding_day=funding_day,
    )


def needed(svc, target, assigned, available, *, month=MAY):
    return svc.calculate_needed(target, Decimal(assigned), Decimal(available), month=month)


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
        assert months_between(date(2024, 5, 1), date(2024, 3, 1)) >= 1


class TestDuty:
    svc = TargetService(repo=None)  # type: ignore[arg-type]

    def duty(self, target, assigned="0", available="0", month=MAY):
        return self.svc.duty(
            target, assigned=Decimal(assigned), available=Decimal(available), month=month
        )

    def test_monthly_duty_is_the_amount(self):
        assert self.duty(make_target("monthly_funding", "500")) == Decimal("500")

    def test_weekly_duty_counts_the_weekday_occurrences_four_and_five(self):
        t = make_target("weekly_funding", "50", weekday=FRIDAY)
        assert self.duty(t, month=MAY) == Decimal("250")
        assert self.duty(t, month=JUNE) == Decimal("200")

    def test_weekly_february_2027_has_four_of_every_weekday(self):
        for weekday in range(7):
            t = make_target("weekly_funding", "10", weekday=weekday)
            assert self.duty(t, month=date(2027, 2, 1)) == Decimal("40")

    def test_weekly_without_a_weekday_is_refused(self):
        with pytest.raises(InvariantViolation):
            self.duty(make_target("weekly_funding", "50"))

    def test_undated_savings_needs_the_shortfall_and_ignores_assigned(self):
        t = make_target("savings_balance", "1000")
        assert self.duty(t, assigned="400", available="600") == Decimal("400")
        assert self.duty(t, assigned="0", available="600") == Decimal("400")

    def test_undated_savings_clamps_at_zero(self):
        assert self.duty(make_target("savings_balance", "600"), available="700") == Decimal("0")

    def test_dated_savings_paces_from_the_opening_balance(self):
        # 1200 by November, viewed in May: six months, 200 a month.
        t = make_target("savings_balance", "1200", date(2026, 11, 1))
        assert self.duty(t, assigned="0", available="0") == Decimal("200")

    def test_dated_savings_assigning_half_the_pace_leaves_half(self):
        """The drift case. The old form divided the POST-assignment shortfall
        by the months left, so assigning 100 of a 200 pace read as
        (1200 − 100) / 6 ≈ 183 still owed — every dollar assigned moved the
        goalpost. Measured from the opening balance, the duty stays 200 and
        `calculate_needed` says 100."""
        t = make_target("savings_balance", "1200", date(2026, 11, 1))
        assert self.duty(t, assigned="100", available="100") == Decimal("200")
        assert needed(self.svc, t, "100", "100") == Decimal("100")

    def test_dated_savings_past_due_asks_the_whole_shortfall_once(self):
        t = make_target("savings_balance", "600", date(2025, 1, 1))
        # months_between floors at 1 — the whole shortfall, not a divide by zero.
        assert self.duty(t, assigned="0", available="100") == Decimal("500")

    def test_a_cards_negative_available_asks_for_more_on_purpose(self):
        t = make_target("savings_balance", "300")
        assert self.duty(t, available="-50") == Decimal("350")


class TestCalculateStatus:
    def setup_method(self):
        self.svc = TargetService(MagicMock())

    def test_monthly_funding_funded(self):
        assert status(self.svc, make_target("monthly_funding", "500"), "500", "500") == "funded"

    def test_monthly_funding_underfunded(self):
        t = make_target("monthly_funding", "500")
        assert status(self.svc, t, "400", "400") == "underfunded"

    def test_monthly_funding_overfunded(self):
        t = make_target("monthly_funding", "500")
        assert status(self.svc, t, "600", "600") == "overfunded"

    def test_monthly_funding_just_at_threshold(self):
        t = make_target("monthly_funding", "500")
        assert status(self.svc, t, "525", "525") == "funded"
        assert status(self.svc, t, "525.01", "525.01") == "overfunded"

    def test_savings_balance_is_judged_on_the_balance_not_the_assignment(self):
        # $400 assigned and spent again: the balance is short and the pill
        # must say so, whatever was assigned this month.
        t = make_target("savings_balance", "1000")
        assert status(self.svc, t, "400", "0") == "underfunded"

    def test_savings_balance_funded_once_the_balance_arrives(self):
        assert status(self.svc, make_target("savings_balance", "1000"), "0", "1000") == "funded"

    def test_savings_balance_overfunded_reads_the_balance_too(self):
        t = make_target("savings_balance", "1000")
        assert status(self.svc, t, "0", "1100") == "overfunded"

    def test_weekly_funding_funded_and_underfunded_on_the_month_duty(self):
        t = make_target("weekly_funding", "50", weekday=FRIDAY)
        assert status(self.svc, t, "250", "250", month=MAY) == "funded"
        assert status(self.svc, t, "200", "200", month=MAY) == "underfunded"
        assert status(self.svc, t, "200", "200", month=JUNE) == "funded"

    def test_overfunded_reads_duty_not_amount_for_weekly(self):
        # 250 is the May duty for a $50 Friday target: five Fridays. It used
        # to read overfunded against the raw 50.
        t = make_target("weekly_funding", "50", weekday=FRIDAY)
        assert status(self.svc, t, "250", "250", month=MAY) == "funded"
        assert status(self.svc, t, "270", "270", month=MAY) == "overfunded"


class TestPending:
    """Unmet before the funding day is pending, not underfunded. Past months
    are never pending; future months always are."""

    def setup_method(self):
        self.svc = TargetService(MagicMock())
        self.t = make_target("monthly_funding", "500")

    def test_pending_before_funding_day_in_the_current_month(self):
        today = date(2026, 5, 6)
        assert status(self.svc, self.t, "0", "0", today=today, funding_day=15) == "pending"

    def test_underfunded_on_the_funding_day_itself(self):
        today = date(2026, 5, 15)
        assert status(self.svc, self.t, "0", "0", today=today, funding_day=15) == "underfunded"

    def test_never_pending_in_a_past_month(self):
        today = date(2026, 6, 2)
        assert (
            status(self.svc, self.t, "0", "0", month=MAY, today=today, funding_day=28)
            == "underfunded"
        )

    def test_pending_in_a_future_month(self):
        today = date(2026, 4, 30)
        assert status(self.svc, self.t, "0", "0", month=MAY, today=today, funding_day=1) == (
            "pending"
        )

    def test_check_after_day_overrides_the_budget_day(self):
        today = date(2026, 5, 10)
        later = make_target("monthly_funding", "500", check_after_day=20)
        earlier = make_target("monthly_funding", "500", check_after_day=5)
        assert status(self.svc, later, "0", "0", today=today, funding_day=1) == "pending"
        assert status(self.svc, earlier, "0", "0", today=today, funding_day=28) == "underfunded"

    def test_pending_is_never_reported_when_nothing_is_needed(self):
        today = date(2026, 5, 1)
        assert status(self.svc, self.t, "500", "500", today=today, funding_day=28) == "funded"

    def test_a_pending_target_still_reports_what_it_needs(self):
        # Fill Underfunded reads this; the nag is held back, the duty is not.
        assert needed(self.svc, self.t, "0", "0") == Decimal("500")


class TestThePillPredictsFillUnderfunded:
    """The budget row's pill exists to say what Fill Underfunded will do.

    Both derive from `duty`, so they cannot disagree about it. The invariant
    that follows: "underfunded or pending" and "there is still something to
    assign" are the same statement.
    """

    svc = TargetService(repo=None)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "target",
        [
            make_target("monthly_funding", "100"),
            make_target("weekly_funding", "25", weekday=FRIDAY),
            make_target("savings_balance", "1000"),
            make_target("savings_balance", "600", date(2026, 11, 1)),
        ],
        ids=["monthly", "weekly", "savings", "dated-savings"],
    )
    @pytest.mark.parametrize(
        ("assigned", "available"),
        [("0", "0"), ("50", "50"), ("100", "100"), ("150", "150"), ("0", "500"), ("0", "1100")],
    )
    @pytest.mark.parametrize("funding_day", [1, 28])
    def test_every_shape_agrees(self, target, assigned, available, funding_day):
        verdict = status(
            self.svc,
            target,
            assigned,
            available,
            today=date(2026, 5, 15),
            funding_day=funding_day,
        )
        owed = needed(self.svc, target, assigned, available)
        assert (verdict in ("underfunded", "pending")) == (owed > 0)


class TestMeasuresBalance:
    svc = TargetService(repo=None)  # type: ignore[arg-type]

    def test_only_an_undated_savings_balance_reads_available(self):
        assert self.svc.measures_balance(make_target("savings_balance", "1"))
        assert not self.svc.measures_balance(make_target("savings_balance", "1", date(2026, 6, 1)))
        assert not self.svc.measures_balance(make_target("monthly_funding", "1"))
        assert not self.svc.measures_balance(make_target("weekly_funding", "1", weekday=0))


class TestMonthlyPace:
    """The pace a wish can count on — exactly the duty, or None for an
    undated savings goal, which has no pace. The old divergence (a dated
    savings goal paced here but filled whole by Fill Underfunded) is gone:
    the duty itself paces now."""

    def setup_method(self):
        self.svc = TargetService(repo=MagicMock())

    def pace(self, target, assigned="0", available="0", month=MAY):
        return self.svc.monthly_pace(
            target, assigned=Decimal(assigned), available=Decimal(available), month=month
        )

    def test_monthly_and_weekly_are_their_duty(self):
        assert self.pace(make_target("monthly_funding", "100")) == Decimal("100")
        assert self.pace(make_target("weekly_funding", "25", weekday=FRIDAY)) == Decimal("125")

    def test_a_dated_savings_goal_paces_by_its_date_and_so_does_fill_underfunded(self):
        t = make_target("savings_balance", "1200", date(2026, 11, 1))
        assert self.pace(t) == Decimal("200")
        assert needed(self.svc, t, "0", "0") == Decimal("200")

    def test_an_undated_savings_goal_has_no_pace(self):
        assert self.pace(make_target("savings_balance", "1000")) is None


class TestValidate:
    def test_weekly_requires_weekday(self):
        with pytest.raises(InvariantViolation, match="weekday|day of the week"):
            TargetService.validate("weekly_funding", None, check_after_day=None, weekday=None)

    def test_only_savings_may_carry_a_date(self):
        with pytest.raises(InvariantViolation, match="target date"):
            TargetService.validate(
                "monthly_funding", date(2026, 6, 1), check_after_day=None, weekday=None
            )
        TargetService.validate(
            "savings_balance", date(2026, 6, 1), check_after_day=None, weekday=None
        )

    def test_the_retired_type_is_refused(self):
        with pytest.raises(InvariantViolation, match="must be one of"):
            TargetService.validate("needed_for_spending", None, check_after_day=None, weekday=None)

    def test_day_fields_are_bounded(self):
        # 31 is a real day of the month and is accepted; is_pending clamps it
        # to each month's own length. 32 is not a day at all.
        TargetService.validate("monthly_funding", None, check_after_day=31, weekday=None)
        with pytest.raises(InvariantViolation):
            TargetService.validate("monthly_funding", None, check_after_day=32, weekday=None)
        with pytest.raises(InvariantViolation):
            TargetService.validate("monthly_funding", None, check_after_day=0, weekday=None)
        with pytest.raises(InvariantViolation):
            TargetService.validate("weekly_funding", None, check_after_day=None, weekday=7)
