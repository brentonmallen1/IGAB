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
    limit: str | None = None,
) -> MagicMock:
    t = MagicMock()
    t.target_type = target_type
    t.target_amount = Decimal(amount)
    t.target_date = target_date
    t.weekday = weekday
    t.check_after_day = check_after_day
    t.target_limit = Decimal(limit) if limit is not None else None
    return t


def status(svc, target, assigned, available, *, activity="0", month=MAY, today=None, funding_day=1):
    return svc.calculate_status(
        target,
        Decimal(assigned),
        Decimal(available),
        activity=Decimal(activity),
        month=month,
        today=today or month.replace(day=15),
        funding_day=funding_day,
    )


def needed(svc, target, assigned, available, *, activity="0", month=MAY):
    return svc.calculate_needed(
        target, Decimal(assigned), Decimal(available), activity=Decimal(activity), month=month
    )


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

    def duty(self, target, assigned="0", available="0", month=MAY, activity="0"):
        return self.svc.duty(
            target,
            assigned=Decimal(assigned),
            activity=Decimal(activity),
            available=Decimal(available),
            month=month,
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

    def pace(self, target, assigned="0", available="0", month=MAY, activity="0"):
        return self.svc.monthly_pace(
            target,
            assigned=Decimal(assigned),
            activity=Decimal(activity),
            available=Decimal(available),
            month=month,
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


class TestTargetAssigned:
    """What Auto-assign's "target amounts" sets a category's assigned to.

    A SET, not a top-up: a paced target reads its month's ask even when that
    is below what was assigned. Only an undated savings balance is topped up
    and never lowered — it has no monthly figure, only a balance to reach.
    """

    def ask(self, target, assigned, available, *, month=MAY, activity="0"):
        svc = TargetService(MagicMock())
        return svc.target_assigned(
            target,
            assigned=Decimal(assigned),
            activity=Decimal(activity),
            available=Decimal(available),
            month=month,
        )

    def test_monthly_reads_the_amount_up_or_down(self):
        t = make_target("monthly_funding", "500.00")
        assert self.ask(t, "100.00", "100.00") == Decimal("500.00")
        assert self.ask(t, "650.00", "650.00") == Decimal("500.00"), "over-assigned comes down"

    def test_weekly_counts_the_weekdays_in_the_month(self):
        t = make_target("weekly_funding", "50.00", weekday=FRIDAY)
        assert self.ask(t, "0", "0", month=MAY) == Decimal("250.00")
        assert self.ask(t, "0", "0", month=JUNE) == Decimal("200.00")

    def test_dated_savings_reads_the_months_pace_in_cents(self):
        # 1000 to go from an opening of 0, over months_between(MAY, Aug 1).
        t = make_target("savings_balance", "1000.00", date(2026, 8, 1))
        months = months_between(MAY, date(2026, 8, 1))
        expected = (Decimal("1000.00") / months).quantize(Decimal("0.01"))
        assert self.ask(t, "0", "0") == expected
        assert self.ask(t, "0", "0").as_tuple().exponent == -2

    def test_undated_savings_tops_up_to_the_balance(self):
        t = make_target("savings_balance", "1000.00")
        assert self.ask(t, "100.00", "600.00") == Decimal("500.00"), "100 + the 400 short"
        assert self.ask(t, "100.00", "1200.00") == Decimal("100.00"), "never lowered"

    def test_lowering_stops_at_what_the_envelope_still_holds(self):
        # Target 100, assigned 160, 140 spent: 20 left. Taking 60 would leave
        # it 40 red; it gives back the 20.
        t = make_target("monthly_funding", "100.00")
        assert self.ask(t, "160.00", "20.00") == Decimal("140.00")
        assert self.ask(t, "160.00", "-5.00") == Decimal("160.00"), "already red: nothing to take"


class TestReturnable:
    """What Reduce Overfunded hands back (`TargetService.returnable`).

    The duty cases moved here from test_assign_strategies.py when the strategy
    stopped deciding the amount: it pulled back to a duty passed in, which
    could not say "never below the stop"."""

    def back(self, target, assigned, available, *, activity="0", month=MAY):
        return TargetService(MagicMock()).returnable(
            target,
            assigned=Decimal(assigned),
            activity=Decimal(activity),
            available=Decimal(available),
            month=month,
        )

    def test_a_weekly_target_comes_back_to_its_duty_not_its_weekly_figure(self):
        # $50 every Friday in a five-Friday May is a $250 duty; pulling back to
        # $50 stripped four fifths of a correctly funded envelope.
        t = make_target("weekly_funding", "50", weekday=FRIDAY)
        assert self.back(t, "300", "300") == Decimal("50")
        assert self.back(t, "250", "250") == Decimal("0")

    def test_bounded_by_what_is_still_in_the_envelope(self):
        # Assigned 300 over a duty of 100, but only 50 left unspent: 50 back.
        t = make_target("monthly_funding", "100")
        assert self.back(t, "300", "50") == Decimal("50")
        assert self.back(t, "300", "-5") == Decimal("0"), "already red: nothing to take"

    def test_a_short_target_returns_nothing(self):
        assert self.back(make_target("monthly_funding", "100"), "40", "40") == Decimal("0")

    def test_an_undated_savings_goal_comes_back_to_its_goal_not_below_it(self):
        """$1,000 goal holding $1,200, $300 of it assigned this month. Reduce
        Overfunded used to give back all $300 — the duty of a met balance goal
        is zero — and left the goal $100 short; it returns the $200 above."""
        t = make_target("savings_balance", "1000")
        assert self.back(t, "300", "1200") == Decimal("200")

    def test_money_carried_in_above_a_ceiling_is_not_this_months_to_return(self):
        t = make_target("savings_balance", "1000")
        assert self.back(t, "0", "1200") == Decimal("0")
        assert self.back(t, "50", "1200") == Decimal("50")


def D2(s: str) -> Decimal:
    return Decimal(s)


class TestTargetLimit:
    """ "$100 a month, stop at $1,000": a monthly or weekly target with a cap.

    The month asks for the rate until the balance CARRIED IN reaches the stop,
    an envelope holding the stop reads funded, and nothing pulls it back below
    the stop. Figures are (assigned, activity, available); what was carried in
    is available − assigned − activity."""

    svc = TargetService(repo=None)  # type: ignore[arg-type]

    @staticmethod
    def capped(rate="100.00", limit="1000.00"):
        return make_target("monthly_funding", rate, limit=limit)

    def duty(self, t, assigned="0", activity="0", available="0", month=MAY):
        return self.svc.duty(
            t,
            assigned=Decimal(assigned),
            activity=Decimal(activity),
            available=Decimal(available),
            month=month,
        )

    def ask(self, t, assigned, activity, available, month=MAY):
        return self.svc.target_assigned(
            t,
            assigned=Decimal(assigned),
            activity=Decimal(activity),
            available=Decimal(available),
            month=month,
        )

    # ── the duty ──────────────────────────────────────────────────────────

    def test_carried_in_well_below_the_stop_asks_for_the_rate(self):
        assert self.duty(self.capped()) == Decimal("100.00")
        assert self.duty(self.capped(), available="500.00") == Decimal("100.00")

    def test_carried_in_close_to_the_stop_asks_only_for_the_gap(self):
        assert self.duty(self.capped(), available="960.00") == Decimal("40.00")

    def test_carried_in_at_or_above_the_stop_asks_for_nothing(self):
        assert self.duty(self.capped(), available="1000.00") == Decimal("0")
        assert self.duty(self.capped(), available="1250.00") == Decimal("0")

    def test_spending_this_month_does_not_raise_the_ask(self):
        """Carried in 1,000, spent 300: the duty reads what came IN, so it is
        still zero — not the 100 a balance-measured reading would refill."""
        t = self.capped()
        assert self.duty(t, activity="-300.00", available="700.00") == Decimal("0")
        assert needed(self.svc, t, "0", "700.00", activity="-300.00") == Decimal("0")
        assert status(self.svc, t, "0", "700.00", activity="-300.00") == "funded"

    def test_spending_while_short_still_asks_only_for_the_gap(self):
        # Carried in 960, spent 500: the gap to the stop on the way in was 40.
        t = self.capped()
        assert self.duty(t, activity="-500.00", available="460.00") == Decimal("40.00")
        assert needed(self.svc, t, "0", "460.00", activity="-500.00") == Decimal("40.00")

    def test_an_overspent_opening_asks_for_the_full_rate(self):
        # A negative carry-in (an imported or card-corrected envelope) is
        # further from the stop, never closer: the rate, not rate + deficit.
        assert self.duty(self.capped(), available="-50.00") == Decimal("100.00")

    def test_without_a_stop_nothing_changes(self):
        t = make_target("monthly_funding", "100.00")
        assert self.duty(t, available="5000.00") == Decimal("100.00")

    def test_weekly_with_a_stop_caps_the_months_weeks(self):
        # $25 every Friday: May asks 125 (five Fridays), June 100 (four).
        t = make_target("weekly_funding", "25.00", weekday=FRIDAY, limit="300.00")
        assert self.duty(t, available="200.00", month=MAY) == Decimal("100.00")
        assert self.duty(t, available="100.00", month=MAY) == Decimal("125.00")
        assert self.duty(t, available="250.00", month=JUNE) == Decimal("50.00")
        assert self.duty(t, available="300.00", month=JUNE) == Decimal("0")

    def test_a_cent_short_asks_for_a_cent(self):
        t = self.capped(rate="33.33")
        assert self.duty(t, available="999.99") == Decimal("0.01")
        assert self.ask(t, "0", "0", "999.99") == Decimal("0.01")
        assert self.ask(t, "0", "0", "999.99").as_tuple().exponent == -2

    # ── needed and the verdict ────────────────────────────────────────────

    def test_money_arriving_this_month_counts_toward_the_stop(self):
        # Carried in 950, a 40 refund landed: the duty is 50, but only 10 more
        # reaches the stop, and that is all Fill Underfunded moves.
        t = self.capped()
        assert needed(self.svc, t, "0", "990.00", activity="40.00") == Decimal("10.00")

    def test_what_was_assigned_is_credited(self):
        assert needed(self.svc, self.capped(), "60.00", "60.00") == Decimal("40.00")
        assert status(self.svc, self.capped(), "0", "0") == "underfunded"

    def test_holding_the_stop_is_funded_however_little_was_assigned(self):
        assert status(self.svc, self.capped(), "0", "1000.00") == "funded"
        assert status(self.svc, self.capped(), "0", "1050.00") == "funded", "inside the band"

    def test_overfunded_only_past_the_stop_by_more_than_the_band(self):
        assert status(self.svc, self.capped(), "0", "1050.01") == "overfunded"
        assert status(self.svc, self.capped(), "1200.00", "1200.00") == "overfunded"

    def test_assigning_ahead_of_the_rate_toward_the_stop_is_not_overfunding(self):
        """300 against a $100/mo rate reads overfunded without a stop; with
        one, it is money on its way to the stop."""
        assert status(self.svc, self.capped(), "300.00", "300.00") == "funded"
        uncapped = make_target("monthly_funding", "100.00")
        assert status(self.svc, uncapped, "300.00", "300.00") == "overfunded"

    def test_monthly_pace_is_the_capped_duty(self):
        pace = self.svc.monthly_pace(
            self.capped(),
            assigned=D2("0"),
            activity=D2("0"),
            available=D2("960.00"),
            month=MAY,
        )
        assert pace == D2("40.00")

    # ── Target amount and Reduce Overfunded ───────────────────────────────

    def test_target_amount_fills_the_rate_or_the_gap(self):
        assert self.ask(self.capped(), "0", "0", "0") == Decimal("100.00")
        assert self.ask(self.capped(), "0", "0", "960.00") == Decimal("40.00")
        assert self.ask(self.capped(), "0", "40.00", "990.00") == Decimal("10.00")

    def test_target_amount_comes_back_down_to_the_stop_and_no_further(self):
        """1,200 assigned from nothing: the rate is 100, but the envelope comes
        back to the 1,000 stop — not to 100, which would empty it."""
        assert self.ask(self.capped(), "1200.00", "0", "1200.00") == Decimal("1000.00")
        # Carried in 900, 300 assigned: the 200 above the stop comes back.
        assert self.ask(self.capped(), "300.00", "0", "1200.00") == Decimal("100.00")

    def test_target_amount_leaves_money_on_its_way_to_the_stop(self):
        assert self.ask(self.capped(), "300.00", "0", "300.00") == Decimal("300.00")

    def test_spent_money_is_not_counted_as_above_the_stop(self):
        # Carried in 1,000, 100 assigned, 80 spent: 1,020 — 20 above.
        assert self.ask(self.capped(), "100.00", "-80.00", "1020.00") == Decimal("80.00")

    def test_reduce_overfunded_stops_at_the_stop(self):
        back = TargetService(MagicMock()).returnable
        t = self.capped()
        zero = D2("0")
        assert back(t, assigned=D2("1200"), activity=zero, available=D2("1200"), month=MAY) == (
            D2("200")
        )
        assert back(t, assigned=D2("300"), activity=zero, available=D2("300"), month=MAY) == zero
        # Carried in above the stop, nothing assigned this month: not ours.
        assert back(t, assigned=zero, activity=zero, available=D2("1200"), month=MAY) == zero


class TestValidateTheLimit:
    def test_only_monthly_and_weekly_may_stop(self):
        TargetService.validate(
            "monthly_funding", None, check_after_day=None, weekday=None, target_limit=D2("1")
        )
        TargetService.validate(
            "weekly_funding", None, check_after_day=None, weekday=4, target_limit=D2("1")
        )
        with pytest.raises(InvariantViolation, match="monthly or weekly"):
            TargetService.validate(
                "savings_balance", None, check_after_day=None, weekday=None, target_limit=D2("1")
            )

    @pytest.mark.parametrize("limit", ["0", "-10"])
    def test_the_stop_is_more_than_zero(self, limit):
        with pytest.raises(InvariantViolation, match="more than zero"):
            TargetService.validate(
                "monthly_funding", None, check_after_day=None, weekday=None, target_limit=D2(limit)
            )
