"""One rate conversion, shared by the schedule and the liability page.

This was written eight times before it had a home: six in the amortization
service as `annual_rate / 100 / 12`, twice in the liabilities API as
`balance * rate / 1200`.
"""

from datetime import date
from decimal import Decimal

from igab.domain.interest import (
    ZERO,
    chargeable_rate,
    interest_for_month,
    monthly_interest,
    monthly_rate,
)


def test_monthly_rate_is_the_annual_percentage_over_twelve():
    assert monthly_rate(Decimal("6")) == Decimal("6") / Decimal("100") / Decimal("12")


def test_monthly_rate_is_not_quantized():
    """Load-bearing: a schedule multiplies this by a falling balance for up to
    360 months and rounds each month. Rounding the rate first would compound
    a rounding error across the life of a mortgage."""
    rate = monthly_rate(Decimal("6.5"))
    assert rate != rate.quantize(Decimal("0.01"))


def test_monthly_interest_is_cents():
    """6% a year on 2,690 is 13.45 a month."""
    assert monthly_interest(Decimal("2690.00"), Decimal("6")) == Decimal("13.45")


def test_monthly_interest_is_the_one_rule_the_schedule_and_the_api_share():
    """The schedule's `quantize_cents(balance * monthly_rate)` and the API's
    old `quantize_cents(balance * rate / 1200)` were two spellings of this.
    Both now route here, so they cannot round a month differently."""
    balance, annual = Decimal("248900.00"), Decimal("6.125")
    from igab.domain.money import quantize_cents

    assert monthly_interest(balance, annual) == quantize_cents(balance * monthly_rate(annual))
    assert monthly_interest(balance, annual) == quantize_cents(balance * annual / Decimal("1200"))


def test_a_zero_rate_costs_nothing():
    assert monthly_interest(Decimal("2690.00"), Decimal("0")) == Decimal("0.00")


# ─── What THIS month is charged ──────────────────────────────────────────────
# `chargeable_rate` and `interest_for_month`: the estimate charged the
# post-payment balance and charged a 0% promo month at the full rate.

SIX = Decimal("6")


class TestInterestForMonth:
    def test_the_month_is_charged_on_what_it_opened_owing(self):
        """24,000 at 6% is 120.00 — the figure the estimate read as 117.50
        once a 500 payment had landed."""
        assert interest_for_month(Decimal("24000.00"), SIX) == Decimal("120.00")

    def test_it_is_cents(self):
        assert interest_for_month(Decimal("23100.00"), SIX) == Decimal("115.50")
        assert interest_for_month(Decimal("248900.00"), Decimal("6.125")) == Decimal("1270.43")

    def test_it_is_monthly_interest_on_a_positive_base(self):
        """One rounding rule: the schedule, the page and this month's charge
        cannot round a month differently."""
        for owed in ("0.01", "1.00", "2690.00", "248900.00"):
            assert interest_for_month(Decimal(owed), SIX) == monthly_interest(Decimal(owed), SIX)

    def test_half_a_cent_rounds_to_even(self):
        """1.00 at 6% is 0.005 and 3.00 is 0.015: banker's rounding, the
        rule `quantize_cents` applies everywhere money rounds."""
        assert interest_for_month(Decimal("1.00"), SIX) == Decimal("0.00")
        assert interest_for_month(Decimal("3.00"), SIX) == Decimal("0.02")
        assert interest_for_month(Decimal("5.00"), SIX) == Decimal("0.02")

    def test_a_cent_owed_costs_nothing_visible(self):
        assert interest_for_month(Decimal("0.01"), Decimal("29.99")) == Decimal("0.00")

    def test_nothing_owed_at_the_open_costs_nothing(self):
        assert interest_for_month(Decimal("0"), SIX) == Decimal("0.00")
        assert interest_for_month(Decimal("0.00"), SIX) == Decimal("0.00")

    def test_a_ledger_in_credit_earns_nothing_from_the_lender(self):
        """Negative owed is an overpayment, not a debt: zero, never a
        negative charge that would lower the balance."""
        assert interest_for_month(Decimal("-50.00"), SIX) == Decimal("0.00")
        assert interest_for_month(Decimal("-0.01"), SIX) == Decimal("0.00")

    def test_a_zero_rate_costs_nothing(self):
        assert interest_for_month(Decimal("24000.00"), ZERO) == Decimal("0.00")

    def test_the_answer_is_always_cents(self):
        for owed in ("-50", "0", "1", "24000"):
            result = interest_for_month(Decimal(owed), SIX)
            assert result == result.quantize(Decimal("0.01"))
            assert result.as_tuple().exponent == -2


class TestChargeableRate:
    def test_no_rate_is_no_answer(self):
        assert chargeable_rate(None, None, date(2026, 3, 1)) is None
        assert chargeable_rate(None, date(2026, 12, 31), date(2026, 3, 1)) is None

    def test_without_a_promo_the_rate_applies(self):
        assert chargeable_rate(SIX, None, date(2026, 3, 1)) == SIX

    def test_a_zero_rate_stays_zero(self):
        assert chargeable_rate(ZERO, None, date(2026, 3, 1)) == ZERO

    def test_a_month_the_promo_covers_is_free(self):
        """Zero, not None: the terms are known and say the month is free."""
        assert chargeable_rate(SIX, date(2026, 12, 31), date(2026, 3, 1)) == ZERO

    def test_a_promo_ending_on_the_months_last_day_covers_it(self):
        """The boundary: "applies only after promo_end_date". Ending on 31
        March leaves no March day after it."""
        assert chargeable_rate(SIX, date(2026, 3, 31), date(2026, 3, 1)) == ZERO
        assert chargeable_rate(SIX, date(2026, 3, 31), date(2026, 4, 1)) == SIX

    def test_february_ends_on_its_own_last_day(self):
        assert chargeable_rate(SIX, date(2026, 2, 28), date(2026, 2, 1)) == ZERO
        assert chargeable_rate(SIX, date(2024, 2, 28), date(2024, 2, 1)) == SIX, "leap year"
        assert chargeable_rate(SIX, date(2024, 2, 29), date(2024, 2, 1)) == ZERO

    def test_a_promo_ending_partway_through_charges_the_month(self):
        """The conservative reading: a few days of interest high is
        reconciled down; low reads the debt as smaller than it is."""
        assert chargeable_rate(SIX, date(2026, 3, 30), date(2026, 3, 1)) == SIX
        assert chargeable_rate(SIX, date(2026, 3, 15), date(2026, 3, 1)) == SIX
        assert chargeable_rate(SIX, date(2026, 3, 1), date(2026, 3, 1)) == SIX

    def test_a_promo_that_ended_before_the_month_charges_it(self):
        assert chargeable_rate(SIX, date(2026, 2, 28), date(2026, 3, 1)) == SIX
        assert chargeable_rate(SIX, date(2020, 1, 1), date(2026, 3, 1)) == SIX

    def test_any_day_names_its_month(self):
        """The service asks with today's date; the answer is the month's."""
        for day in (1, 15, 31):
            assert chargeable_rate(SIX, date(2026, 3, 31), date(2026, 3, day)) == ZERO
            assert chargeable_rate(SIX, date(2026, 3, 30), date(2026, 3, day)) == SIX

    def test_composes_into_a_free_promo_month(self):
        rate = chargeable_rate(SIX, date(2026, 12, 31), date(2026, 3, 1))
        assert rate is not None
        assert interest_for_month(Decimal("24000.00"), rate) == Decimal("0.00")
