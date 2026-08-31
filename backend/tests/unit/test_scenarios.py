"""The Tools tab's calculators — presentation over the amortization engine."""

from datetime import date
from decimal import Decimal

import pytest

from igab.guide.scenarios import (
    LoanCandidate,
    emergency_fund,
    loan_compare,
    pay_vs_save,
    payoff_plan,
)
from igab.services.amortization import CascadeDebt, future_value_monthly, level_payment


def D(s: str) -> Decimal:
    return Decimal(s)


TODAY = date(2026, 8, 26)


class TestLevelPayment:
    def test_standard_table_value_rounded_up(self):
        # 10,000 at 6% over 12 months: the tables say 860.66 (nearest); we
        # round up so twelve payments actually close it.
        assert level_payment(D("10000"), D("6"), 12) == D("860.67")

    def test_thirty_year_mortgage(self):
        # 300,000 at 6.5% over 360 months: 1,896.20 in the tables, 1,896.21 up.
        assert level_payment(D("300000"), D("6.5"), 360) == D("1896.21")

    def test_zero_rate_spreads_the_principal(self):
        assert level_payment(D("10000"), D("0"), 12) == D("833.34")

    def test_the_term_holds_with_a_smaller_final_payment(self):
        payment = level_payment(D("10000"), D("6"), 12)
        from igab.services.amortization import amortization_schedule

        result = amortization_schedule(D("10000"), D("6"), payment, TODAY)
        assert len(result.schedule) == 12
        assert result.schedule[-1].payment < payment

    def test_bad_inputs(self):
        with pytest.raises(ValueError):
            level_payment(D("100"), D("5"), 0)
        with pytest.raises(ValueError):
            level_payment(D("-100"), D("5"), 12)


class TestFutureValue:
    def test_zero_rate_is_contributions(self):
        assert future_value_monthly(D("100"), D("0"), 12) == D("1200.00")

    def test_compounds_monthly_on_the_prior_balance(self):
        # 12%/yr = 1%/mo: month 1 = 100; month 2 = 101 + 100.
        assert future_value_monthly(D("100"), D("12"), 2) == D("201.00")

    def test_no_months_is_nothing(self):
        assert future_value_monthly(D("100"), D("5"), 0) == D("0.00")


class TestPayVsSave:
    def test_paying_a_high_rate_card_beats_a_modest_savings_rate(self):
        r = pay_vs_save(D("3410"), D("22.9"), D("85"), D("100"), D("4"), TODAY)
        assert r.favours == "pay"
        assert r.debt_interest_saved > r.savings_interest_earned
        assert r.months_sooner > 0
        assert r.pay_payoff_date is not None

    def test_breakeven_brackets_the_tie_to_the_basis_point(self):
        r = pay_vs_save(D("3410"), D("22.9"), D("85"), D("100"), D("4"), TODAY)
        assert r.breakeven_apy is not None
        # At the named rate saving at least ties; one basis point lower it does not.
        at = pay_vs_save(D("3410"), D("22.9"), D("85"), D("100"), r.breakeven_apy, TODAY)
        assert at.savings_interest_earned >= at.debt_interest_saved
        below = pay_vs_save(
            D("3410"), D("22.9"), D("85"), D("100"), r.breakeven_apy - D("0.01"), TODAY
        )
        assert below.savings_interest_earned < below.debt_interest_saved

    def test_a_zero_rate_debt_saves_no_interest_so_breakeven_is_zero(self):
        r = pay_vs_save(D("1000"), D("0"), D("100"), D("50"), D("4"), TODAY)
        assert r.debt_interest_saved == D("0")
        assert r.breakeven_apy == D("0")
        assert r.favours == "save"

    def test_a_minimum_under_the_interest_still_gets_an_answer(self):
        # Baseline never pays off; the horizon falls back to the paying arm.
        r = pay_vs_save(D("1000"), D("24"), D("10"), D("100"), D("4"), TODAY)
        assert r.baseline_never_pays_off
        assert not r.pay_never_pays_off
        assert r.horizon_months == r.pay_months
        assert r.favours == "pay"

    def test_negative_inputs_are_rejected(self):
        with pytest.raises(ValueError):
            pay_vs_save(D("1000"), D("5"), D("50"), D("-1"), D("4"), TODAY)


class TestLoanCompare:
    def test_derives_the_payment_from_a_term(self):
        c = loan_compare([LoanCandidate("A", D("10000"), D("6"), term_months=12)], TODAY)
        a = c.loans[0]
        assert a.payment == D("860.67")
        assert a.months == 12
        assert a.total_cost == D("10000") + a.total_interest

    def test_fees_count_toward_total_cost(self):
        c = loan_compare(
            [
                LoanCandidate(
                    "Cheap rate, big fee", D("10000"), D("5"), term_months=12, fees=D("500")
                ),
                LoanCandidate("Dearer rate, no fee", D("10000"), D("7"), term_months=12),
            ],
            TODAY,
        )
        costs = {o.name: o.total_cost for o in c.loans}
        assert costs["Dearer rate, no fee"] < costs["Cheap rate, big fee"]
        assert c.cheapest == "Dearer rate, no fee"

    def test_tie_breaks_on_lower_payment_then_name(self):
        c = loan_compare(
            [
                LoanCandidate("B", D("1000"), D("0"), term_months=10),
                LoanCandidate("A", D("1000"), D("0"), term_months=10),
                LoanCandidate("C", D("1000"), D("0"), term_months=20),
            ],
            TODAY,
        )
        # All cost exactly 1000; C's payment is lower; A beats B on name.
        assert c.cheapest == "C"

    def test_a_loan_that_never_pays_off_cannot_be_cheapest(self):
        c = loan_compare(
            [
                LoanCandidate("Stalled", D("1000"), D("24"), payment=D("10")),
                LoanCandidate("Real", D("1000"), D("24"), term_months=12),
            ],
            TODAY,
        )
        assert c.loans[0].never_pays_off
        assert c.cheapest == "Real"
        only = loan_compare([LoanCandidate("Stalled", D("1000"), D("24"), payment=D("10"))], TODAY)
        assert only.cheapest is None

    def test_term_or_payment_is_required(self):
        with pytest.raises(ValueError):
            loan_compare([LoanCandidate("A", D("1000"), D("5"))], TODAY)


class TestEmergencyFund:
    def test_ceil_rounds_a_partial_month_up(self):
        p = emergency_fund(D("0"), D("33.33"), 3, D("30"), TODAY)
        assert p.target == D("99.99")
        assert p.months_to_fund == 4  # 99.99 / 30 = 3.33 → 4
        assert p.funded_by == date(2026, 12, 26)

    def test_exact_division_does_not_round_up(self):
        p = emergency_fund(D("0"), D("100"), 3, D("100"), TODAY)
        assert p.months_to_fund == 3

    def test_zero_contribution_is_no_date_not_infinity(self):
        p = emergency_fund(D("100"), D("1000"), 3, D("0"), TODAY)
        assert p.gap == D("2900.00")
        assert p.months_to_fund is None
        assert p.funded_by is None

    def test_already_funded(self):
        p = emergency_fund(D("5000"), D("1000"), 3, D("100"), TODAY)
        assert p.gap == D("0")
        assert p.months_to_fund == 0
        assert p.funded_by == TODAY

    def test_no_essentials_means_no_target_not_zero(self):
        for essentials in (None, D("0")):
            p = emergency_fund(D("500"), essentials, 6, D("100"), TODAY)
            assert p.target is None
            assert p.gap is None
            assert p.months_to_fund is None

    def test_unknown_current_gives_a_target_but_no_gap(self):
        p = emergency_fund(None, D("1000"), 3, D("100"), TODAY)
        assert p.target == D("3000.00")
        assert p.gap is None

    def test_bad_inputs(self):
        with pytest.raises(ValueError):
            emergency_fund(D("0"), D("100"), 0, D("10"), TODAY)
        with pytest.raises(ValueError):
            emergency_fund(D("0"), D("100"), 3, D("-10"), TODAY)


class TestPayoffPlan:
    def test_returns_both_strategies_and_a_flat_baseline(self):
        debts = [
            CascadeDebt("visa", "Visa", D("3410"), D("22.9"), D("85")),
            CascadeDebt("car", "Car", D("14200"), D("6.4"), D("310")),
        ]
        plan = payoff_plan(debts, D("200"), TODAY)
        assert plan.avalanche.order == "avalanche"
        assert plan.snowball.order == "snowball"
        assert plan.minimums_only.total_interest >= plan.avalanche.total_interest
        assert plan.minimums_only.total_interest >= plan.snowball.total_interest
        assert plan.extra == D("200.00")
