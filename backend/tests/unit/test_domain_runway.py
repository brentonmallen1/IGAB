"""The runway rule (`domain.runway`): how long the money lasts if income
stopped. Figures are round enough to check on paper; the household is
invented."""

from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from igab.domain.runway import (
    DAYS_PER_MONTH,
    PICKER_MONEY,
    Holdings,
    LinePoint,
    MoneyBasis,
    Runway,
    SpendingBasis,
    burn_down,
    card_debt,
    default_basis,
    figure,
    money_for,
    runway,
)

TODAY = date(2026, 9, 26)


def holdings(**overrides) -> Holdings:
    """$6,000 in the budget's cash (a $1,000 Emergency fund envelope among
    it), $500 owed on a Sapphire Visa, $4,000 in a Cascade Point HYSA marked
    as the fund, $2,000 in another off-budget savings account, $1,000
    declared as kept elsewhere."""
    base = {
        "cash": D("6000.00"),
        "card_debt": D("500.00"),
        "fund": D("6000.00"),  # 1,000 envelope + 4,000 HYSA + 1,000 declared
        "fund_accounts": D("4000.00"),
        "declared": D("1000.00"),
        "savings_accounts": D("6000.00"),  # the HYSA + 2,000 elsewhere
    }
    return Holdings(**{**base, **overrides})


class TestRunway:
    def test_money_over_a_month_to_one_decimal(self):
        assert runway(D("6000"), D("2000"), TODAY).months == D("3.0")
        assert runway(D("5000"), D("2000"), TODAY).months == D("2.5")
        assert runway(D("1000"), D("3000"), TODAY).months == D("0.3")

    def test_the_date_is_today_plus_the_months(self):
        # Three months of 30.4375 days: 91.3 days, 91 whole.
        assert runway(D("6000"), D("2000"), TODAY).runs_out_on == TODAY + timedelta(days=91)
        # Twelve months is a year to the day.
        assert runway(D("12000"), D("1000"), TODAY).runs_out_on == TODAY + timedelta(days=365)

    def test_the_date_reads_the_unrounded_months(self):
        # 2.96 and 3.04 both print 3.0; they do not run out on the same day.
        low = runway(D("2960"), D("1000"), TODAY)
        high = runway(D("3040"), D("1000"), TODAY)
        assert low.months == high.months == D("3.0")
        assert low.runs_out_on < high.runs_out_on

    def test_zero_money_has_run_out_today(self):
        assert runway(D("0"), D("2000"), TODAY) == Runway(D("0.0"), TODAY)

    def test_negative_money_has_run_out_today(self):
        # Card debt larger than the cash: the money is already gone.
        assert runway(D("-450.00"), D("2000"), TODAY) == Runway(D("0.0"), TODAY)

    def test_a_cent_left_still_runs_out_today_at_a_real_pace(self):
        result = runway(D("0.01"), D("3000"), TODAY)
        assert result.months == D("0.0")
        assert result.runs_out_on == TODAY

    def test_nothing_spent_has_no_runway(self):
        assert runway(D("6000"), D("0"), TODAY) == Runway(None, None)

    def test_refunds_beating_spending_have_no_runway(self):
        assert runway(D("6000"), D("-20"), TODAY) == Runway(None, None)

    def test_an_unknown_month_has_no_runway(self):
        # Nothing tagged Essential: unknown, never "infinite" or zero.
        assert runway(D("6000"), None, TODAY) == Runway(None, None)

    def test_an_unknown_fund_has_no_runway(self):
        assert runway(None, D("2000"), TODAY) == Runway(None, None)

    def test_nothing_spent_wins_over_nothing_left(self):
        # No pace to run out at, even with no money: there is no date to state.
        assert runway(D("-100"), D("0"), TODAY) == Runway(None, None)

    def test_a_date_past_the_calendar_is_none_not_a_crash(self):
        result = runway(D("9999999999999"), D("0.01"), TODAY)
        assert result.months is not None
        assert result.runs_out_on is None


class TestCardDebt:
    def test_owed_is_the_negative_balances_flipped(self):
        assert card_debt([D("-300.00"), D("-200.00")]) == D("500.00")

    def test_a_card_in_credit_lends_nothing(self):
        # A $150 overpayment on one card does not hide $500 owed on another.
        assert card_debt([D("150.00"), D("-500.00")]) == D("500.00")

    def test_no_cards_owe_nothing(self):
        assert card_debt([]) == D("0.00")


class TestMoney:
    def test_checking_is_the_cash_less_the_cards(self):
        assert money_for(MoneyBasis.CHECKING, holdings()) == D("5500.00")

    def test_the_fund_adds_only_what_it_holds_outside_the_cash(self):
        # The $1,000 envelope is already in the cash; the HYSA and the
        # declared amount are not. Adding the fund's whole total would count
        # the envelope twice.
        assert money_for(MoneyBasis.WITH_FUND, holdings()) == D("10500.00")

    def test_all_savings_adds_every_off_budget_savings_account_and_the_declared(self):
        assert money_for(MoneyBasis.WITH_SAVINGS, holdings()) == D("12500.00")

    def test_the_fund_alone_is_its_total_less_the_cards(self):
        assert money_for(MoneyBasis.FUND, holdings()) == D("5500.00")

    def test_each_wider_choice_holds_at_least_the_narrower(self):
        h = holdings()
        checking, fund, savings = (money_for(m, h) for m in PICKER_MONEY)
        assert checking is not None and fund is not None and savings is not None
        assert checking <= fund <= savings

    def test_no_fund_chosen_is_unknown_not_zero(self):
        h = holdings(fund=None, fund_accounts=D("0"), declared=D("0"))
        assert money_for(MoneyBasis.WITH_FUND, h) is None
        assert money_for(MoneyBasis.FUND, h) is None
        # The cash and the savings do not need a fund.
        assert money_for(MoneyBasis.CHECKING, h) == D("5500.00")
        assert money_for(MoneyBasis.WITH_SAVINGS, h) == D("11500.00")

    def test_card_debt_larger_than_the_cash_goes_negative(self):
        h = holdings(card_debt=D("7000.00"))
        assert money_for(MoneyBasis.CHECKING, h) == D("-1000.00")
        assert runway(money_for(MoneyBasis.CHECKING, h), D("2000"), TODAY).months == D("0.0")

    def test_a_zero_fund_is_chosen_and_counts_zero(self):
        h = holdings(fund=D("0"), fund_accounts=D("0"), declared=D("0"), card_debt=D("0"))
        assert money_for(MoneyBasis.FUND, h) == D("0.00")
        assert runway(money_for(MoneyBasis.FUND, h), D("2000"), TODAY).months == D("0.0")


#: Spending per month on each basis: all 3,000, cost of living 2,500,
#: essentials 2,000.
MONTHLY = {
    SpendingBasis.ALL: D("3000"),
    SpendingBasis.COST_OF_LIVING: D("2500"),
    SpendingBasis.ESSENTIALS: D("2000"),
}

#: Money on each choice from `holdings()`: 5,500 / 10,500 / 12,500 / 5,500.
EXPECTED_MONTHS = {
    (SpendingBasis.ALL, MoneyBasis.CHECKING): D("1.8"),
    (SpendingBasis.ALL, MoneyBasis.WITH_FUND): D("3.5"),
    (SpendingBasis.ALL, MoneyBasis.WITH_SAVINGS): D("4.2"),
    (SpendingBasis.ALL, MoneyBasis.FUND): D("1.8"),
    (SpendingBasis.COST_OF_LIVING, MoneyBasis.CHECKING): D("2.2"),
    (SpendingBasis.COST_OF_LIVING, MoneyBasis.WITH_FUND): D("4.2"),
    (SpendingBasis.COST_OF_LIVING, MoneyBasis.WITH_SAVINGS): D("5.0"),
    (SpendingBasis.COST_OF_LIVING, MoneyBasis.FUND): D("2.2"),
    (SpendingBasis.ESSENTIALS, MoneyBasis.CHECKING): D("2.8"),
    (SpendingBasis.ESSENTIALS, MoneyBasis.WITH_FUND): D("5.2"),
    (SpendingBasis.ESSENTIALS, MoneyBasis.WITH_SAVINGS): D("6.2"),
    (SpendingBasis.ESSENTIALS, MoneyBasis.FUND): D("2.8"),
}


class TestFigure:
    @pytest.mark.parametrize(("spending", "money"), list(EXPECTED_MONTHS))
    def test_every_spending_and_money(self, spending, money):
        result = figure(spending, money, MONTHLY[spending], holdings(), TODAY)
        assert result.months == EXPECTED_MONTHS[(spending, money)]
        assert result.spending is spending
        assert result.money is money
        assert result.monthly_spending == MONTHLY[spending]
        assert result.card_debt == D("500.00")

    def test_it_states_the_money_after_the_cards(self):
        result = figure(
            SpendingBasis.ESSENTIALS, MoneyBasis.WITH_FUND, D("2000"), holdings(), TODAY
        )
        assert result.money_total == D("10500.00")

    def test_an_unknown_basis_answers_nothing(self):
        result = figure(SpendingBasis.ESSENTIALS, MoneyBasis.CHECKING, None, holdings(), TODAY)
        assert result.months is None
        assert result.runs_out_on is None
        assert result.money_total == D("5500.00")


class TestBurnDown:
    END = TODAY + timedelta(days=90)

    def test_reaches_zero_on_the_runs_out_date_inside_the_horizon(self):
        line = burn_down(D("4000"), D("2000"), TODAY, self.END)
        out = runway(D("4000"), D("2000"), TODAY).runs_out_on
        assert line == [LinePoint(TODAY, D("4000.00")), LinePoint(out, D("0.00"))]
        assert out == TODAY + timedelta(days=61)

    def test_stops_at_the_horizon_when_the_money_outlasts_it(self):
        # 90 days at $3,043.75 a month (100 a day of 30.4375): 9,000 spent.
        monthly = D("100") * DAYS_PER_MONTH
        line = burn_down(D("12000"), monthly, TODAY, self.END)
        assert line == [LinePoint(TODAY, D("12000.00")), LinePoint(self.END, D("3000.00"))]

    def test_nothing_spent_is_flat(self):
        line = burn_down(D("5000"), D("0"), TODAY, self.END)
        assert line == [LinePoint(TODAY, D("5000.00")), LinePoint(self.END, D("5000.00"))]

    def test_money_already_gone_is_its_starting_point_alone(self):
        assert burn_down(D("-300"), D("2000"), TODAY, self.END) == [LinePoint(TODAY, D("-300.00"))]
        assert burn_down(D("0"), D("2000"), TODAY, self.END) == [LinePoint(TODAY, D("0.00"))]

    def test_unknown_money_draws_nothing(self):
        assert burn_down(None, D("2000"), TODAY, self.END) == []

    def test_an_unknown_month_is_flat_not_missing(self):
        # The picker offers it disabled; the line would be the money standing.
        line = burn_down(D("5000"), None, TODAY, self.END)
        assert [p.balance for p in line] == [D("5000.00"), D("5000.00")]

    def test_runs_out_exactly_on_the_horizon(self):
        # 61 days is exactly where two months at 2,000 lands.
        end = TODAY + timedelta(days=61)
        line = burn_down(D("4000"), D("2000"), TODAY, end)
        assert line[-1] == LinePoint(end, D("0.00"))


class TestDefault:
    def test_essentials_against_the_cash_and_the_fund(self):
        assert default_basis(True, True) == (SpendingBasis.ESSENTIALS, MoneyBasis.WITH_FUND)

    def test_no_fund_falls_back_to_the_cash(self):
        assert default_basis(True, False) == (SpendingBasis.ESSENTIALS, MoneyBasis.CHECKING)

    def test_nothing_tagged_falls_back_to_all_spending(self):
        assert default_basis(False, True) == (SpendingBasis.ALL, MoneyBasis.WITH_FUND)

    def test_both_fall_back_together(self):
        assert default_basis(False, False) == (SpendingBasis.ALL, MoneyBasis.CHECKING)

    def test_the_fund_alone_is_never_a_picker_choice(self):
        assert MoneyBasis.FUND not in PICKER_MONEY
