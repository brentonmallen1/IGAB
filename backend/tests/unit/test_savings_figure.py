"""`domain/savings.py`: every branch of the held figure, on paper.

The worked checks against a real budget are in
tests/integration/test_savings_held.py; these hold the pure arithmetic —
unknown balances, negatives, the floor, the cuts and the rounding.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.savings import (
    HELD_REASON,
    HELD_REASON_LABEL,
    SavingsFigure,
    balance_at,
    held_change,
    held_over,
    month_cuts,
    savings_rates,
    window_cuts,
)

D = Decimal


class TestBalanceAt:
    def test_a_month_end_cut_is_the_pages_available(self):
        assert balance_at(D("500"), D("0")) == D("500")

    def test_later_rows_in_the_month_are_taken_off(self):
        """Available already holds a row dated after the cut; the cut does not."""
        assert balance_at(D("200"), D("-300")) == D("500")

    def test_a_later_refund_is_taken_off_too(self):
        assert balance_at(D("540"), D("40")) == D("500")

    def test_it_may_be_negative(self):
        assert balance_at(D("-80"), D("0")) == D("-80")

    def test_unknown_stays_unknown(self):
        assert balance_at(None, D("0")) is None
        assert balance_at(None, D("-25")) is None

    def test_sub_cent_amounts_are_exact(self):
        assert balance_at(D("100.0050"), D("0.0025")) == D("100.0025")


class TestHeldChange:
    def test_assigning_is_held(self):
        assert held_change(D("0"), D("500")) == D("500")

    def test_spending_lowers_held(self):
        assert held_change(D("500"), D("380")) == D("-120")

    def test_an_overspent_end_floors_at_zero(self):
        """Ready to Assign covered the shortfall: the envelope held 500, now 0."""
        assert held_change(D("500"), D("-80")) == D("-500")

    def test_spending_from_an_empty_envelope_holds_nothing(self):
        assert held_change(D("0"), D("-120")) == D("0")

    def test_a_negative_start_reads_as_zero(self):
        """A month that began overspent was written off; the next starts at 0."""
        assert held_change(D("-300"), D("200")) == D("200")
        assert held_change(D("-300"), D("-50")) == D("0")

    def test_zero_to_zero(self):
        assert held_change(D("0"), D("0")) == D("0")

    @pytest.mark.parametrize(
        ("before", "after"), [(None, D("500")), (D("500"), None), (None, None)]
    )
    def test_an_unknown_end_holds_nothing(self, before, after):
        assert held_change(before, after) == D("0")

    def test_rounding_is_left_to_the_server_edge(self):
        """Held is exact Decimal; serving quantizes."""
        assert held_change(D("0.0049"), D("10.0099")) == D("10.0050")


class TestHeldOver:
    def test_a_known_chain_telescopes_to_its_ends(self):
        chain = [D("100"), D("600"), D("-50"), D("300"), D("250")]
        assert held_over(chain) == held_change(chain[0], chain[-1]) == D("150")

    def test_an_unknown_start_holds_only_the_known_steps(self):
        """Months before the recovered history fall back to flows (held 0);
        the months after still hold what they held."""
        assert held_over([None, D("400"), D("700")]) == D("300")

    def test_an_unknown_in_the_middle_breaks_only_its_two_steps(self):
        assert held_over([D("100"), None, D("700"), D("900")]) == D("200")

    def test_too_short_holds_nothing(self):
        assert held_over([]) == D("0")
        assert held_over([D("500")]) == D("0")


class TestCuts:
    def test_a_calendar_month(self):
        assert window_cuts(date(2026, 3, 1), date(2026, 3, 31)) == [
            date(2026, 2, 28),
            date(2026, 3, 31),
        ]

    def test_month_ends_inside_the_window(self):
        assert window_cuts(date(2026, 1, 1), date(2026, 3, 15)) == [
            date(2025, 12, 31),
            date(2026, 1, 31),
            date(2026, 2, 28),
            date(2026, 3, 15),
        ]

    def test_a_mid_month_start(self):
        assert window_cuts(date(2026, 1, 20), date(2026, 2, 10)) == [
            date(2026, 1, 19),
            date(2026, 1, 31),
            date(2026, 2, 10),
        ]

    def test_one_day(self):
        assert window_cuts(date(2026, 3, 15), date(2026, 3, 15)) == [
            date(2026, 3, 14),
            date(2026, 3, 15),
        ]

    def test_a_window_ending_before_it_starts_is_one_cut(self):
        assert window_cuts(date(2026, 3, 15), date(2026, 3, 1)) == [date(2026, 3, 14)]

    def test_month_cuts_clamp_the_running_month_to_today(self):
        months = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
        assert month_cuts(months, date(2026, 3, 15)) == [
            date(2025, 12, 31),
            date(2026, 1, 31),
            date(2026, 2, 28),
            date(2026, 3, 15),
        ]

    def test_month_cuts_are_the_windows_cuts(self):
        months = [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1)]
        today = date(2026, 1, 9)
        assert month_cuts(months, today) == window_cuts(months[0], today)

    def test_a_month_after_today_holds_nothing(self):
        cuts = month_cuts([date(2026, 3, 1), date(2026, 4, 1)], date(2026, 3, 15))
        assert cuts[-1] == cuts[-2] == date(2026, 3, 15)

    def test_no_months_no_cuts(self):
        assert month_cuts([], date(2026, 3, 15)) == []


class TestSavingsFigure:
    def test_total_is_moved_plus_held(self):
        assert SavingsFigure(moved=D("300"), held=D("-300")).total == D("0")
        assert SavingsFigure(moved=D("0"), held=D("500")).total == D("500")
        assert SavingsFigure(moved=D("-150"), held=D("0")).total == D("-150")


class TestSavingsRates:
    def test_held_joins_both_numerators(self):
        rates = savings_rates(
            {"income": D("5000"), "savings": D("-250"), "debt_principal": D("-500")}, D("250")
        )
        assert rates == {"savings_rate": 0.1, "savings_rate_with_debt": 0.2}

    def test_a_negative_held_lowers_the_rate(self):
        rates = savings_rates({"income": D("1000")}, D("-120"))
        assert rates["savings_rate"] == -0.12

    def test_moved_and_held_can_cancel(self):
        rates = savings_rates({"income": D("1000"), "savings": D("-300")}, D("-300"))
        assert rates == {"savings_rate": 0.0, "savings_rate_with_debt": 0.0}

    def test_no_income_is_no_rate_whatever_is_held(self):
        assert savings_rates({}, D("500")) == {"savings_rate": None, "savings_rate_with_debt": None}
        assert savings_rates({"income": D("0")}, D("500"))["savings_rate"] is None

    def test_held_is_required(self):
        with pytest.raises(TypeError):
            savings_rates({"income": D("1000")})  # type: ignore[call-arg]


def test_the_held_reason_is_not_an_activity_reason():
    """Served as a contributor reason, like the split reasons: no SQL rule
    emits it, so it must not be an `ActivityReason` member."""
    from igab.domain.activity_class import ActivityReason

    assert HELD_REASON not in {r.value for r in ActivityReason}
    assert HELD_REASON_LABEL == "held in a Savings envelope"
