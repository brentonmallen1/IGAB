"""The words the spending-shaped reports share: what "spent" adds up, and
when a payee counts as recurring."""

from decimal import Decimal

import pytest

from igab.domain.spending import RECURRING_FLOOR_MONTHS, recurring_months, spent


class TestSpent:
    def test_outflows_read_positive(self):
        assert spent([Decimal("-60.00"), Decimal("-40.00")]) == Decimal("100.00")

    def test_a_refund_lowers_it(self):
        assert spent([Decimal("-100.00"), Decimal("25.00")]) == Decimal("75.00")

    def test_more_refunded_than_bought_stays_negative(self):
        # Shown signed, never clamped: the total above a list includes it.
        assert spent([Decimal("-20.00"), Decimal("90.00")]) == Decimal("-70.00")

    def test_nothing_is_zero(self):
        assert spent([]) == Decimal("0")


class TestRecurringMonths:
    @pytest.mark.parametrize(
        ("window", "need"),
        [
            # Too short to call anything a habit: the page says "needs 3+".
            (1, None),
            (2, None),
            # The floor holds on short windows…
            (3, 3),
            (4, 3),
            (5, 3),
            (6, 3),
            # …and half the window, rounded up, beyond them.
            (7, 4),
            (12, 6),
            (13, 7),
            (24, 12),
        ],
    )
    def test_half_the_window_and_never_fewer_than_three(self, window, need):
        assert recurring_months(window) == need

    def test_the_floor_is_three(self):
        assert RECURRING_FLOOR_MONTHS == 3
