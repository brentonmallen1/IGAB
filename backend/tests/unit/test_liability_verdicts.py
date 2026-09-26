"""The liability verdicts every page reads from one place
(`services.amortization`): which payoff to state, what paying more buys, and
whether the entered terms describe one loan.

Figures are invented and round; the level payment is the textbook one.
"""

from datetime import date
from decimal import Decimal as D

from igab.services.amortization import (
    AmortizationResult,
    LiveProjection,
    amortization_schedule,
    paydown_gain,
    payoff_verdict,
    terms_check,
)

AS_OF = date(2026, 9, 15)


def _live(never: bool, payoff: date | None) -> LiveProjection:
    return LiveProjection(
        payoff_date=payoff,
        never_pays_off=never,
        typical_payment=D("500"),
        total_interest=None if never else D("100"),
        months=None if never else 12,
    )


def _baseline(never: bool, payoff: date | None) -> AmortizationResult:
    return AmortizationResult(
        schedule=[], never_pays_off=never, payoff_date=payoff, total_interest=D("0")
    )


class TestPayoffVerdict:
    """The Liabilities overview, the account's terms header and the payoff
    pill each chose "live, else minimum" on the client."""

    def test_a_pace_speaks_first(self):
        verdict = payoff_verdict(_live(False, date(2027, 9, 1)), _baseline(False, date(2029, 1, 1)))
        assert (verdict.basis, verdict.payoff_date, verdict.never_pays_off) == (
            "observed",
            date(2027, 9, 1),
            False,
        )

    def test_a_pace_that_never_pays_off_has_no_date_even_when_the_minimum_does(self):
        verdict = payoff_verdict(_live(True, None), _baseline(False, date(2029, 1, 1)))
        assert (verdict.basis, verdict.payoff_date, verdict.never_pays_off) == (
            "observed",
            None,
            True,
        )

    def test_without_a_pace_the_minimum_speaks(self):
        verdict = payoff_verdict(None, _baseline(False, date(2029, 1, 1)))
        assert (verdict.basis, verdict.payoff_date) == ("minimum", date(2029, 1, 1))

    def test_a_minimum_that_never_pays_off(self):
        verdict = payoff_verdict(None, _baseline(True, None))
        assert (verdict.basis, verdict.payoff_date, verdict.never_pays_off) == (
            "minimum",
            None,
            True,
        )

    def test_without_terms_there_is_no_verdict_and_unknown_is_not_never(self):
        verdict = payoff_verdict(None, None)
        assert (verdict.basis, verdict.payoff_date, verdict.never_pays_off) == (None, None, False)


class TestPaydownGain:
    def test_both_pay_off(self):
        """$1,000 at 12%: $400 a month costs $18.26 of interest over three
        payments, $500 costs $15.25 over three (`test_amortization`)."""
        gain = paydown_gain(
            amortization_schedule(D("1000"), D("12"), D("400"), AS_OF),
            amortization_schedule(D("1000"), D("12"), D("500"), AS_OF),
        )
        assert (gain.months_sooner, gain.interest_saved) == (0, D("3.01"))

    def test_against_a_minimum_that_never_pays_off_there_is_no_saving_to_state(self):
        """$10,000 at 24% is $200 of interest a month; the $100 minimum stops
        at its first uncovered month having counted $0. The page quoted
        $0 − the faster schedule's interest: a negative saving."""
        baseline = amortization_schedule(D("10000"), D("24"), D("100"), AS_OF)
        faster = amortization_schedule(D("10000"), D("24"), D("300"), AS_OF)
        assert baseline.never_pays_off and not faster.never_pays_off
        gain = paydown_gain(baseline, faster)
        assert (gain.months_sooner, gain.interest_saved) == (None, None)

    def test_a_minimum_capped_at_fifty_years_is_not_fifty_years_saved(self):
        """$100,000 at 6% on $500.01 retires a cent a month: the schedule
        runs to its cap and its running total is decades of interest."""
        baseline = amortization_schedule(D("100000"), D("6"), D("500.01"), AS_OF)
        faster = amortization_schedule(D("100000"), D("6"), D("800"), AS_OF)
        assert baseline.never_pays_off
        assert paydown_gain(baseline, faster).interest_saved is None

    def test_a_faster_schedule_that_still_never_pays_off(self):
        baseline = amortization_schedule(D("10000"), D("24"), D("100"), AS_OF)
        faster = amortization_schedule(D("10000"), D("24"), D("150"), AS_OF)
        gain = paydown_gain(baseline, faster)
        assert (gain.months_sooner, gain.interest_saved) == (None, None)


class TestTermsCheck:
    """$300,000 at 6% over 360 months levels at $1,798.66 (ceiling of
    1,798.6516)."""

    def check(self, payment: str, **kwargs):
        facts = {
            "original_principal": D("300000"),
            "annual_rate": D("6"),
            "payment": D(payment),
            "term_months": 360,
            "origination_date": None,
        }
        facts.update(kwargs)
        return terms_check(**facts)

    def test_the_level_payment_agrees(self):
        result = self.check("1798.66")
        assert result.level_payment == D("1798.66")
        assert not result.disagree

    def test_within_two_percent_is_rounding_not_a_contradiction(self):
        assert not self.check("1830.00").disagree

    def test_escrow_folded_into_the_payment_disagrees(self):
        assert self.check("2400.00").disagree

    def test_a_payment_well_below_the_level_disagrees_too(self):
        assert self.check("1700.00").disagree

    def test_a_payment_that_never_amortized_the_loan_disagrees(self):
        """The origination replay: $1,000 against $1,500 of monthly interest."""
        result = self.check("1000.00", term_months=None, origination_date=date(2020, 1, 1))
        assert result.implied_never_pays_off is True
        assert result.implied_term_months is None
        assert result.disagree

    def test_the_implied_term_from_origination(self):
        result = self.check("1798.66", origination_date=date(2020, 1, 1))
        assert result.implied_term_months == 360
        assert not result.disagree

    def test_missing_facts_claim_nothing(self):
        result = self.check("2400.00", term_months=None)
        assert (result.level_payment, result.implied_term_months, result.disagree) == (
            None,
            None,
            False,
        )

    def test_no_principal_claims_nothing(self):
        assert not self.check("2400.00", original_principal=D("0")).disagree
