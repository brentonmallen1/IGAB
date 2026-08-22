"""Amortization engine: hand-computed schedules, clamps, and cent exactness.

This math produces the payoff dates, interest totals, and schedule tables
users make real decisions with — every branch is pinned against values
computed by hand (or a standard mortgage table), and the zero-cent-drift
invariant (Σ principal == starting balance, exactly, whenever a loan pays
off) is asserted across shapes.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.services.amortization import (
    add_months,
    amortization_schedule,
    project_payoff,
    quantize_cents,
)


def D(s: str) -> Decimal:
    return Decimal(s)


START = date(2026, 7, 15)


class TestHandComputedSchedule:
    """$1,000 at 12%/yr (1%/mo), $400/mo — three payments, checked by hand."""

    def test_exact_three_month_schedule(self):
        result = amortization_schedule(D("1000.00"), D("12"), D("400.00"), START)

        assert not result.never_pays_off
        assert len(result.schedule) == 3

        m1, m2, m3 = result.schedule
        assert m1.interest_paid == D("10.00")  # 1000 * 1%
        assert m1.principal_paid == D("390.00")
        assert m1.balance == D("610.00")

        assert m2.interest_paid == D("6.10")  # 610 * 1%
        assert m2.principal_paid == D("393.90")
        assert m2.balance == D("216.10")

        assert m3.interest_paid == D("2.16")  # 216.10 * 1% = 2.161 → 2.16
        assert m3.principal_paid == D("216.10"), "final payment clamps to the balance"
        assert m3.balance == D("0.00")

        assert result.total_interest == D("18.26")
        assert result.payoff_date == date(2026, 10, 15)

    def test_zero_cent_drift(self):
        result = amortization_schedule(D("1000.00"), D("12"), D("400.00"), START)
        assert sum((m.principal_paid for m in result.schedule), D("0")) == D("1000.00")

    def test_month_dates_advance_monthly_from_start(self):
        result = amortization_schedule(D("1000.00"), D("12"), D("400.00"), START)
        assert [m.date for m in result.schedule] == [
            date(2026, 8, 15),
            date(2026, 9, 15),
            date(2026, 10, 15),
        ]
        assert [m.month_index for m in result.schedule] == [1, 2, 3]

    def test_final_payment_is_smaller_not_negative(self):
        result = amortization_schedule(D("1000.00"), D("12"), D("400.00"), START)
        last = result.schedule[-1]
        assert last.payment == D("218.26")  # 216.10 principal + 2.16 interest
        assert last.payment < D("400.00")
        assert all(m.balance >= D("0") for m in result.schedule)


class TestNeverPaysOff:
    def test_payment_equal_to_interest(self):
        # 1000 at 12%/yr → 10.00 interest; a 10.00 payment goes nowhere
        result = amortization_schedule(D("1000.00"), D("12"), D("10.00"), START)
        assert result.never_pays_off
        assert result.payoff_date is None
        assert result.schedule == []
        assert result.total_interest == D("0")

    def test_payment_below_interest(self):
        result = amortization_schedule(D("1000.00"), D("12"), D("5.00"), START)
        assert result.never_pays_off

    def test_zero_payment(self):
        result = amortization_schedule(D("1000.00"), D("12"), D("0"), START)
        assert result.never_pays_off

    def test_cap_months_exceeded(self):
        # Payment barely above interest: pays down cents per month, blows the cap
        result = amortization_schedule(
            D("100000.00"), D("12"), D("1000.01"), START, cap_months=120
        )
        assert result.never_pays_off
        assert result.payoff_date is None
        assert len(result.schedule) == 120


class TestZeroRate:
    def test_interest_free_loan(self):
        result = amortization_schedule(D("1000.00"), D("0"), D("100.00"), START)
        assert not result.never_pays_off
        assert len(result.schedule) == 10
        assert result.total_interest == D("0")
        assert all(m.interest_paid == D("0") for m in result.schedule)
        assert sum((m.principal_paid for m in result.schedule), D("0")) == D("1000.00")

    def test_interest_free_with_uneven_final_payment(self):
        result = amortization_schedule(D("250.00"), D("0"), D("100.00"), START)
        assert len(result.schedule) == 3
        assert result.schedule[-1].principal_paid == D("50.00")


class TestTextbookMortgage:
    """$200,000 at 6%/yr over 30 years — standard payment is $1,199.10."""

    def test_thirty_year_mortgage_shape(self):
        result = amortization_schedule(D("200000.00"), D("6"), D("1199.10"), START)
        assert not result.never_pays_off
        # Cent rounding can shift the last payment by a month either way
        assert 358 <= len(result.schedule) <= 362
        # Total interest on this loan is ≈ $231,676
        assert D("230000") < result.total_interest < D("233500")
        assert sum((m.principal_paid for m in result.schedule), D("0")) == D("200000.00")

    def test_extra_payment_saves_months_and_interest(self):
        baseline = amortization_schedule(D("200000.00"), D("6"), D("1199.10"), START)
        with_extra = amortization_schedule(D("200000.00"), D("6"), D("1399.10"), START)
        assert not with_extra.never_pays_off
        # Closed-form check: n = -ln(1 - rB/P)/ln(1+r) ≈ 252 payments with the
        # extra $200 → ~108 months and ~$80k interest saved
        months_saved = len(baseline.schedule) - len(with_extra.schedule)
        assert 105 <= months_saved <= 112
        interest_saved = baseline.total_interest - with_extra.total_interest
        assert D("75000") < interest_saved < D("85000")
        assert sum((m.principal_paid for m in with_extra.schedule), D("0")) == D("200000.00")


class TestEdgeCases:
    def test_zero_balance_already_paid_off(self):
        result = amortization_schedule(D("0"), D("6"), D("100.00"), START)
        assert not result.never_pays_off
        assert result.payoff_date == START
        assert result.schedule == []

    def test_negative_balance_treated_as_paid_off(self):
        result = amortization_schedule(D("-10.00"), D("6"), D("100.00"), START)
        assert not result.never_pays_off
        assert result.schedule == []

    def test_sub_cent_balance_quantized(self):
        result = amortization_schedule(D("100.004"), D("0"), D("100.00"), START)
        assert len(result.schedule) == 1
        assert result.schedule[0].principal_paid == D("100.00")

    def test_negative_rate_rejected(self):
        with pytest.raises(ValueError):
            amortization_schedule(D("1000.00"), D("-1"), D("100.00"), START)

    def test_negative_payment_rejected(self):
        with pytest.raises(ValueError):
            amortization_schedule(D("1000.00"), D("6"), D("-100.00"), START)

    def test_day_clamps_at_short_months(self):
        result = amortization_schedule(D("300.00"), D("0"), D("100.00"), date(2026, 1, 31))
        assert [m.date for m in result.schedule] == [
            date(2026, 2, 28),
            date(2026, 3, 31),
            date(2026, 4, 30),
        ]

    def test_zero_drift_across_shapes(self):
        cases = [
            (D("12345.67"), D("19.99"), D("450.00")),
            (D("500.01"), D("3.5"), D("77.77")),
            (D("99999.99"), D("7.125"), D("1500.00")),
        ]
        for balance, rate, payment in cases:
            result = amortization_schedule(balance, rate, payment, START)
            assert not result.never_pays_off, (balance, rate, payment)
            total_principal = sum((m.principal_paid for m in result.schedule), D("0"))
            assert total_principal == balance, (balance, rate, payment)


class TestAddMonths:
    def test_simple_shift(self):
        assert add_months(date(2026, 7, 15), 1) == date(2026, 8, 15)

    def test_year_rollover(self):
        assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)

    def test_day_clamp_february(self):
        assert add_months(date(2026, 1, 30), 1) == date(2026, 2, 28)
        assert add_months(date(2024, 1, 30), 1) == date(2024, 2, 29)  # leap year


class TestProjectPayoff:
    def test_insufficient_history_returns_none(self):
        assert project_payoff(D("1000.00"), D("12"), [], START) is None
        assert project_payoff(D("1000.00"), D("12"), [D("400.00")], START) is None

    def test_zero_and_negative_payments_do_not_count(self):
        # Balance-increase months are floored to 0 upstream; only positive
        # payments are evidence of paydown velocity.
        payments = [D("0"), D("400.00"), D("0")]
        assert project_payoff(D("1000.00"), D("12"), payments, START) is None

    def test_average_matches_hand_computed_schedule(self):
        # Average of 300 and 500 is 400 → identical to the hand-computed case
        projection = project_payoff(D("1000.00"), D("12"), [D("300.00"), D("500.00")], START)
        assert projection is not None
        assert projection.average_payment == D("400.00")
        assert projection.payoff_date == date(2026, 10, 15)
        assert not projection.never_pays_off

    def test_payments_below_interest_project_never_pays_off(self):
        projection = project_payoff(D("10000.00"), D("24"), [D("100.00"), D("100.00")], START)
        assert projection is not None
        assert projection.never_pays_off
        assert projection.payoff_date is None


class TestQuantizeCents:
    def test_half_even(self):
        assert quantize_cents(D("2.165")) == D("2.16")  # banker's rounding
        assert quantize_cents(D("2.175")) == D("2.18")
        assert quantize_cents(D("2.161")) == D("2.16")
