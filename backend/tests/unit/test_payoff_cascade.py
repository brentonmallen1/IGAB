"""The multi-debt payoff cascade: rollover, ordering, edges, cent exactness.

Avalanche-versus-snowball is a decision people make with real money, so the
rollover mechanics are pinned by hand-traced cases at 0% (where the arithmetic
is checkable in your head) and the single-debt case is held equal, month for
month, to the schedule the liabilities page already trusts.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.minimum_payment import PERCENT_OF_BALANCE, MinimumPaymentRule
from igab.services.amortization import (
    CascadeDebt,
    add_months,
    amortization_schedule,
    cascade_order,
    payoff_cascade,
)


def D(s: str) -> Decimal:
    return Decimal(s)


START = date(2026, 8, 26)


def debt(key: str, balance: str, rate: str, minimum: str, name: str | None = None) -> CascadeDebt:
    return CascadeDebt(
        key=key,
        name=name or key,
        balance=D(balance),
        annual_rate=D(rate),
        minimum_payment=D(minimum),
    )


def by_key(result, key: str):
    return next(d for d in result.debts if d.key == key)


class TestSingleDebtAgreesWithTheSchedule:
    def test_month_for_month_equality_with_extra(self):
        # Minimum 400 plus 100 extra must be the plain 500 schedule.
        one = [debt("a", "1000.00", "12", "400.00")]
        cascade = payoff_cascade(one, D("100.00"), "avalanche", START)
        schedule = amortization_schedule(D("1000.00"), D("12"), D("500.00"), START)

        assert len(cascade.months) == len(schedule.schedule)
        for c, s in zip(cascade.months, schedule.schedule, strict=True):
            assert (c.payment, c.principal_paid, c.interest_paid, c.balance) == (
                s.payment,
                s.principal_paid,
                s.interest_paid,
                s.balance,
            )
        assert cascade.debt_free_date == schedule.payoff_date
        assert cascade.total_interest == schedule.total_interest

    def test_zero_extra_is_the_plain_schedule(self):
        one = [debt("a", "1000.00", "12", "400.00")]
        cascade = payoff_cascade(one, D("0"), "snowball", START)
        schedule = amortization_schedule(D("1000.00"), D("12"), D("400.00"), START)
        assert [m.balance for m in cascade.months] == [m.balance for m in schedule.schedule]
        assert cascade.total_interest == D("18.26")


class TestRollover:
    def test_freed_minimum_rolls_the_month_after_closure(self):
        # A closes in month 1; its 100 joins B's pool from month 2.
        debts = [debt("a", "100.00", "0", "100.00"), debt("b", "500.00", "0", "50.00")]
        result = payoff_cascade(debts, D("0"), "avalanche", START)

        assert by_key(result, "a").months == 1
        # Month 2: 500 - 50 (m1) = 450, then 50 minimum + 100 rolled = 300.
        assert result.months[1].balances["b"] == D("300.00")
        assert by_key(result, "b").months == 4
        assert result.debt_free_date == add_months(START, 4)

    def test_remainder_of_extra_passes_to_the_next_debt_in_the_same_month(self):
        # Snowball attacks A (30) first: 10 minimum, 20 of the 100 extra clears
        # it, the other 80 lands on B in the same month.
        debts = [debt("a", "30.00", "0", "10.00"), debt("b", "500.00", "0", "50.00")]
        result = payoff_cascade(debts, D("100.00"), "snowball", START)

        m1 = result.months[0]
        assert m1.balances["a"] == D("0")
        assert m1.balances["b"] == D("370.00")  # 500 - 50 - 80
        assert m1.payment == D("160.00")  # 10 + 50 + 100
        assert by_key(result, "a").months == 1

    def test_clamped_final_minimum_joins_the_pool_that_month(self):
        # A owes 5 against a 100 minimum: the unused 95 goes to B this month.
        debts = [debt("a", "5.00", "0", "100.00"), debt("b", "500.00", "0", "50.00")]
        result = payoff_cascade(debts, D("0"), "avalanche", START)

        m1 = result.months[0]
        assert m1.payment == D("150.00")  # 5 + 50 + 95
        assert m1.balances["b"] == D("355.00")  # 500 - 50 - 95
        assert by_key(result, "a").total_principal == D("5.00")

    def test_without_rolling_the_baseline_is_minimums_forever(self):
        debts = [debt("a", "100.00", "0", "100.00"), debt("b", "500.00", "0", "50.00")]
        rolled = payoff_cascade(debts, D("0"), "avalanche", START)
        flat = payoff_cascade(debts, D("0"), "avalanche", START, roll_freed=False)
        assert by_key(rolled, "b").months == 4
        assert by_key(flat, "b").months == 10
        assert flat.debt_free_date == add_months(START, 10)


class TestOrders:
    def test_avalanche_attacks_highest_rate_first(self):
        debts = [debt("car", "14200.00", "6.4", "310"), debt("visa", "3410.00", "22.9", "85")]
        assert [d.key for d in cascade_order(debts, "avalanche")] == ["visa", "car"]

    def test_snowball_attacks_smallest_balance_first(self):
        debts = [debt("car", "14200.00", "6.4", "310"), debt("visa", "3410.00", "22.9", "85")]
        assert [d.key for d in cascade_order(debts, "snowball")] == ["visa", "car"]
        debts2 = [debt("big", "900.00", "26", "25"), debt("small", "890.00", "22.9", "85")]
        assert [d.key for d in cascade_order(debts2, "snowball")] == ["small", "big"]

    def test_rate_tie_breaks_on_smaller_balance_then_name(self):
        debts = [
            debt("z", "500.00", "10", "10", name="Zed"),
            debt("a", "500.00", "10", "10", name="Alpha"),
            debt("m", "100.00", "10", "10", name="Mid"),
        ]
        assert [d.key for d in cascade_order(debts, "avalanche")] == ["m", "a", "z"]

    def test_balance_tie_breaks_on_higher_rate_then_name(self):
        debts = [
            debt("z", "500.00", "5", "10", name="Zed"),
            debt("a", "500.00", "5", "10", name="Alpha"),
            debt("h", "500.00", "9", "10", name="Hot"),
        ]
        assert [d.key for d in cascade_order(debts, "snowball")] == ["h", "a", "z"]

    def test_unknown_order_is_rejected(self):
        with pytest.raises(ValueError):
            cascade_order([], "fastest")  # type: ignore[arg-type]

    def test_snowball_never_costs_less_interest_than_avalanche_here(self):
        debts = [debt("visa", "1000.00", "24", "30"), debt("loan", "200.00", "6", "30")]
        avalanche = payoff_cascade(debts, D("50.00"), "avalanche", START)
        snowball = payoff_cascade(debts, D("50.00"), "snowball", START)
        assert avalanche.total_interest <= snowball.total_interest
        # And the psychological payoff is real: snowball clears something first.
        first_avalanche = min(d.months for d in avalanche.debts)
        first_snowball = min(d.months for d in snowball.debts)
        assert first_snowball <= first_avalanche


class TestEdges:
    def test_extra_exceeding_total_clears_everything_in_month_one_and_pays_only_what_is_owed(self):
        debts = [debt("a", "100.00", "0", "10.00"), debt("b", "50.00", "0", "10.00")]
        result = payoff_cascade(debts, D("1000.00"), "avalanche", START)
        assert len(result.months) == 1
        assert result.months[0].payment == D("150.00")
        assert result.total_paid == D("150.00")
        assert result.debt_free_date == add_months(START, 1)
        assert all(d.months == 1 for d in result.debts)

    def test_a_zero_balance_debt_is_already_paid_and_frees_nothing(self):
        debts = [debt("paid", "0", "20", "200.00"), debt("b", "300.00", "0", "100.00")]
        result = payoff_cascade(debts, D("0"), "avalanche", START)
        paid = by_key(result, "paid")
        assert paid.months == 0
        assert paid.payoff_date == START
        assert not paid.never_pays_off
        # If 200 had been "freed", B would have cleared in one month.
        assert by_key(result, "b").months == 3

    def test_nothing_owed_at_all(self):
        result = payoff_cascade([debt("a", "0", "10", "50")], D("100"), "snowball", START)
        assert result.months == []
        assert result.debt_free_date == START
        assert not result.never_pays_off
        assert result.total_paid == D("0")

    def test_a_stalled_card_grows_until_the_cascade_reaches_it_then_clears(self):
        # 24% on 1000 is 20 a month; a 10 minimum loses ground. Once B closes
        # its 100 rolls onto A and the balance turns.
        debts = [debt("a", "1000.00", "24", "10.00"), debt("b", "100.00", "0", "100.00")]
        result = payoff_cascade(debts, D("0"), "avalanche", START)
        assert result.months[0].balances["a"] == D("1010.00")
        assert result.months[1].balances["a"] < D("1010.00")
        assert not result.never_pays_off
        assert by_key(result, "a").payoff_date is not None

    def test_never_pays_off_when_nothing_moves(self):
        result = payoff_cascade([debt("a", "1000.00", "24", "10.00")], D("0"), "avalanche", START)
        assert result.never_pays_off
        assert result.debt_free_date is None
        assert by_key(result, "a").never_pays_off
        assert len(result.months) == 1  # reported, not looped

    def test_cap_reports_never_pays_off(self):
        # 1 a month against 1000 at 1% would take far longer than the cap.
        result = payoff_cascade(
            [debt("a", "1000.00", "1", "1.00")], D("0"), "avalanche", START, cap_months=12
        )
        assert result.never_pays_off
        assert len(result.months) == 12
        assert by_key(result, "a").payoff_date is None

    def test_negative_inputs_are_rejected(self):
        with pytest.raises(ValueError):
            payoff_cascade([debt("a", "100", "5", "10")], D("-1"), "avalanche", START)
        with pytest.raises(ValueError):
            payoff_cascade([debt("a", "100", "-5", "10")], D("0"), "avalanche", START)
        with pytest.raises(ValueError):
            payoff_cascade([debt("a", "100", "5", "-10")], D("0"), "avalanche", START)


class TestExactness:
    DEBTS = [
        debt("visa", "3410.00", "22.9", "85.00"),
        debt("store", "890.00", "26", "25.00"),
        debt("car", "14200.00", "6.4", "310.00"),
    ]

    @pytest.mark.parametrize("order", ["avalanche", "snowball"])
    def test_principal_sums_to_each_starting_balance_to_the_cent(self, order):
        result = payoff_cascade(self.DEBTS, D("200.00"), order, START)
        assert not result.never_pays_off
        for d in self.DEBTS:
            assert by_key(result, d.key).total_principal == d.balance
        assert result.months[-1].balance == D("0")

    @pytest.mark.parametrize("order", ["avalanche", "snowball"])
    def test_totals_equal_the_sum_of_months(self, order):
        result = payoff_cascade(self.DEBTS, D("200.00"), order, START)
        assert result.total_paid == sum((m.payment for m in result.months), D("0"))
        assert result.total_interest == sum((m.interest_paid for m in result.months), D("0"))
        assert result.total_paid == result.total_interest + sum(
            (d.total_principal for d in result.debts), D("0")
        )
        assert all(m.payment == m.principal_paid + m.interest_paid for m in result.months)

    def test_every_amount_is_whole_cents(self):
        result = payoff_cascade(self.DEBTS, D("200.00"), "avalanche", START)
        for m in result.months:
            for amount in (m.payment, m.principal_paid, m.interest_paid, m.balance):
                assert amount == amount.quantize(D("0.01"))


class TestARuleInTheCascade:
    """A card whose minimum is a percentage sits beside a loan whose payment
    is a number, and both step through the same month."""

    def rule(self):
        return MinimumPaymentRule(kind=PERCENT_OF_BALANCE, percent=D("3"), floor=D("25"))

    def test_a_percent_card_and_a_fixed_loan_both_close(self):
        debts = [
            CascadeDebt("card", "Sapphire Visa", D("4000.00"), D("22"), self.rule()),
            CascadeDebt("loan", "Auto", D("6000.00"), D("6"), D("250.00")),
        ]
        result = payoff_cascade(debts, D("300.00"), "avalanche", START)
        assert result.debt_free_date is not None
        assert by_key(result, "card").payoff_date is not None
        assert by_key(result, "loan").payoff_date is not None

    def test_the_cards_minimum_falls_while_the_loans_does_not(self):
        debts = [
            CascadeDebt("card", "Sapphire Visa", D("4000.00"), D("22"), self.rule()),
            CascadeDebt("loan", "Auto", D("6000.00"), D("6"), D("250.00")),
        ]
        # No extra: each debt gets exactly its own minimum, so the monthly
        # total is the sum of the two and falls only because the card's does.
        result = payoff_cascade(debts, D("0"), "avalanche", START, roll_freed=False)
        first, second, third = (m.payment for m in result.months[:3])
        assert first > second > third

    def test_the_freed_payment_is_the_last_one_actually_asked_for(self):
        """On closure the cascade rolls "what this debt was consuming"
        forward. A declining rule has no single figure, and re-evaluating one
        against a zero balance would roll nothing — so the last amount charged
        is what moves."""
        card = MinimumPaymentRule(kind=PERCENT_OF_BALANCE, percent=D("10"), floor=D("50"))
        debts = [
            CascadeDebt("card", "Sapphire Visa", D("300.00"), D("0"), card),
            CascadeDebt("loan", "Auto", D("5000.00"), D("0"), D("100.00")),
        ]
        rolled = payoff_cascade(debts, D("0"), "snowball", START)
        flat = payoff_cascade(debts, D("0"), "snowball", START, roll_freed=False)

        # The card closes; rolling its freed payment onto the loan has to make
        # the loan finish sooner than not rolling it.
        assert by_key(rolled, "card").payoff_date is not None
        assert by_key(rolled, "loan").months < by_key(flat, "loan").months

    def test_a_rule_with_no_floor_stalls_rather_than_looping(self):
        unusable = MinimumPaymentRule(kind=PERCENT_OF_BALANCE, percent=D("3"))
        debts = [CascadeDebt("card", "Sapphire Visa", D("4000.00"), D("22"), unusable)]
        result = payoff_cascade(debts, D("0"), "avalanche", START)
        assert by_key(result, "card").never_pays_off

    def test_extra_still_rides_on_top_of_a_declining_minimum(self):
        """`minimum + extra`, where the minimum is now asked of the rule. A
        percent-rule card must still receive the whole extra payment, or
        payoff stops converging."""
        debts = [CascadeDebt("card", "Sapphire Visa", D("4000.00"), D("22"), self.rule())]
        with_extra = payoff_cascade(debts, D("400.00"), "avalanche", START)
        without = payoff_cascade(debts, D("0"), "avalanche", START)
        assert by_key(with_extra, "card").months < by_key(without, "card").months
