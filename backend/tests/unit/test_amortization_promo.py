"""Promotional-financing math: 0% through the promo window, contract rate
after, and the promo-end outlook (balance at deadline, deferred interest).
All values hand-computed; the zero-cent-drift invariant carries over."""

from datetime import date
from decimal import Decimal

from igab.services.amortization import (
    ZERO,
    amortization_schedule_with_promo,
    promo_outlook,
)


def D(s: str) -> Decimal:
    return Decimal(s)


START = date(2026, 1, 15)
PROMO_END = date(2026, 7, 1)  # payments land on the 15th: 5 fall inside


class TestPromoSchedule:
    def test_segment_boundary_is_exact(self):
        """$1,200 at 12%/yr, $100/mo, 0% through Jul 1: five interest-free
        payments, then interest starts on the $700 remainder."""
        result = amortization_schedule_with_promo(D("1200.00"), D("12"), D("100.00"), START, PROMO_END)

        promo_part = result.schedule[:5]
        assert all(m.interest_paid == ZERO for m in promo_part)
        assert promo_part[-1].balance == D("700.00")

        first_post = result.schedule[5]
        assert first_post.date == date(2026, 7, 15)
        assert first_post.interest_paid == D("7.00")  # 700 × 1%
        assert first_post.principal_paid == D("93.00")

        # Month indexes stay continuous across the seam
        assert [m.month_index for m in result.schedule[:7]] == [1, 2, 3, 4, 5, 6, 7]
        # Exactness invariant: principal sums to the starting balance
        assert not result.never_pays_off
        assert sum(m.principal_paid for m in result.schedule) == D("1200.00")

    def test_cleared_inside_promo_window_pays_zero_interest(self):
        result = amortization_schedule_with_promo(D("300.00"), D("12"), D("100.00"), START, PROMO_END)
        assert not result.never_pays_off
        assert result.total_interest == ZERO
        assert result.payoff_date == date(2026, 4, 15)
        assert len(result.schedule) == 3

    def test_payment_date_on_promo_end_is_still_interest_free(self):
        on_boundary = amortization_schedule_with_promo(
            D("200.00"), D("12"), D("100.00"), START, date(2026, 2, 15)
        )
        assert on_boundary.schedule[0].interest_paid == ZERO

        day_before = amortization_schedule_with_promo(
            D("200.00"), D("12"), D("100.00"), START, date(2026, 2, 14)
        )
        assert day_before.schedule[0].interest_paid == D("2.00")  # 200 × 1%

    def test_never_pays_off_when_post_promo_interest_swallows_payment(self):
        """$50/mo dents the balance during the promo but can't cover the 2%/mo
        interest afterwards — reported honestly."""
        result = amortization_schedule_with_promo(
            D("10000.00"), D("24"), D("50.00"), START, PROMO_END
        )
        assert result.never_pays_off
        assert result.payoff_date is None
        # The promo payments still happened
        assert result.schedule[-1].balance == D("9750.00")


class TestPromoOutlook:
    def test_balances_at_promo_end_for_both_paces(self):
        outlook = promo_outlook(
            balance=D("1200.00"),
            annual_rate=D("12"),
            minimum_payment=D("100.00"),
            average_payment=D("200.00"),
            as_of=START,
            promo_end_date=PROMO_END,
            deferred_interest=False,
        )
        assert outlook.months_until_promo_end == 6
        assert outlook.balance_at_promo_end_minimum == D("700.00")
        assert outlook.balance_at_promo_end_live == D("200.00")
        assert outlook.clears_before_promo is False
        assert outlook.deferred_interest_estimate is None

    def test_clears_at_live_pace_even_when_minimum_would_not(self):
        outlook = promo_outlook(
            balance=D("300.00"),
            annual_rate=D("12"),
            minimum_payment=D("50.00"),
            average_payment=D("200.00"),
            as_of=START,
            promo_end_date=PROMO_END,
            deferred_interest=False,
        )
        assert outlook.balance_at_promo_end_minimum == D("50.00")
        assert outlook.balance_at_promo_end_live == ZERO
        assert outlook.clears_before_promo is True

    def test_deferred_interest_estimate_hand_computed(self):
        """Elapsed months accrue on the original principal (1500 × 1% × 3);
        remaining months accrue on the declining balance at the live pace
        (12 + 10 + 8 + 6 + 4)."""
        outlook = promo_outlook(
            balance=D("1200.00"),
            annual_rate=D("12"),
            minimum_payment=D("100.00"),
            average_payment=D("200.00"),
            as_of=START,
            promo_end_date=PROMO_END,
            deferred_interest=True,
            origination_date=date(2025, 10, 15),
            original_principal=D("1500.00"),
        )
        assert outlook.deferred_interest_estimate == D("85.00")

    def test_deferred_estimate_falls_back_without_history_or_principal(self):
        """No live pace → minimum; no original principal → current balance."""
        outlook = promo_outlook(
            balance=D("1200.00"),
            annual_rate=D("12"),
            minimum_payment=D("100.00"),
            average_payment=None,
            as_of=START,
            promo_end_date=PROMO_END,
            deferred_interest=True,
        )
        # Declining at 100/mo: 12 + 11 + 10 + 9 + 8 = 50; no elapsed part
        assert outlook.deferred_interest_estimate == D("50.00")
        assert outlook.balance_at_promo_end_live is None
        assert outlook.clears_before_promo is False
