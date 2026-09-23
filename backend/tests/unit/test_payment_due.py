"""Which due-date rules a card may store.

The rule is the whole feature on the write side: the arithmetic that turns it
into a date lives on the client (see domain/payment_due.py's docstring for
why), so what this module has to get right is refusing a rule nothing could
evaluate. Every case here is a line.
"""

from datetime import date

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.domain.payment_due import (
    CYCLE_DAYS,
    DAY_OF_MONTH,
    MAX_CYCLE_DAYS,
    MIN_CYCLE_DAYS,
    validate_payment_due,
)


def check(kind, *, day=None, cycle_days=None, anchor=None):
    validate_payment_due(kind=kind, day=day, cycle_days=cycle_days, anchor=anchor)


class TestADayOfTheMonth:
    def test_is_accepted(self):
        check(DAY_OF_MONTH, day=17)

    def test_may_be_absent(self):
        """The ordinary state of a card nobody has typed a due date into.
        Refusing it here would mean a card could not be saved at all until
        someone found its statement."""
        check(DAY_OF_MONTH, day=None)

    @pytest.mark.parametrize("day", [0, 32, -1])
    def test_refuses_a_day_no_month_has(self, day):
        with pytest.raises(InvariantViolation, match="day of the month"):
            check(DAY_OF_MONTH, day=day)

    def test_ignores_cycle_fields_left_behind(self):
        """Switching back from a cycle leaves the old figures in the row. They
        mean nothing under this kind, and the kind is what decides — which is
        the reason the kind is stored at all rather than inferred from which
        columns happen to be filled."""
        check(DAY_OF_MONTH, day=17, cycle_days=31, anchor=date(2026, 9, 3))


class TestACycle:
    def test_needs_both_halves(self):
        check(CYCLE_DAYS, cycle_days=31, anchor=date(2026, 9, 3))

    def test_refuses_a_length_with_no_anchor(self):
        """A cycle length alone says how often, never from when."""
        with pytest.raises(InvariantViolation, match="last due date"):
            check(CYCLE_DAYS, cycle_days=31)

    def test_refuses_an_anchor_with_no_length(self):
        with pytest.raises(InvariantViolation, match="last due date"):
            check(CYCLE_DAYS, anchor=date(2026, 9, 3))

    @pytest.mark.parametrize("days", [0, -31])
    def test_refuses_a_cycle_that_never_advances(self, days):
        """Zero is the one that matters: the client walks the anchor forward
        by whole cycles to reach today, and a step of zero days never gets
        there."""
        with pytest.raises(InvariantViolation, match="between"):
            check(CYCLE_DAYS, cycle_days=days, anchor=date(2026, 9, 3))

    @pytest.mark.parametrize("days", [MIN_CYCLE_DAYS - 1, MAX_CYCLE_DAYS + 1, 365])
    def test_refuses_a_cycle_outside_the_bounds(self, days):
        with pytest.raises(InvariantViolation, match="between"):
            check(CYCLE_DAYS, cycle_days=days, anchor=date(2026, 9, 3))

    @pytest.mark.parametrize("days", [MIN_CYCLE_DAYS, 28, 31, MAX_CYCLE_DAYS])
    def test_accepts_the_bounds_themselves(self, days):
        check(CYCLE_DAYS, cycle_days=days, anchor=date(2026, 9, 3))


def test_an_unknown_kind_is_refused_rather_than_read_as_the_default():
    """A typo'd kind reaching storage would render as "no due date on file",
    which is the silent wrong answer this column exists to prevent."""
    with pytest.raises(InvariantViolation, match="two ways"):
        check("every_full_moon", day=17)
