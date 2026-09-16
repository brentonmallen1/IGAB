"""The one savings-rate division, shared by the report and the Guide.

Nothing held here (`held=D("0")`); held's own branches are in test_savings_figure.py."""

from decimal import Decimal

from igab.domain.savings import savings_rates

D = Decimal


def test_both_rates_divide_outflow_magnitudes_by_income():
    rates = savings_rates(
        {"income": D("6000"), "savings": D("-900"), "debt_principal": D("-300")}, D("0")
    )
    assert rates == {"savings_rate": 0.15, "savings_rate_with_debt": 0.2}


def test_no_income_is_no_rate_not_zero():
    assert savings_rates({"savings": D("-100")}, D("0")) == {
        "savings_rate": None,
        "savings_rate_with_debt": None,
    }
    assert savings_rates({"income": D("-50")}, D("0"))["savings_rate"] is None


def test_money_drawn_back_out_of_savings_is_a_negative_rate():
    rates = savings_rates({"income": D("1000"), "savings": D("250")}, D("0"))
    assert rates["savings_rate"] == -0.25


def test_spending_and_transfers_do_not_enter_either_rate():
    rates = savings_rates(
        {"income": D("1000"), "spending": D("-800"), "transfer_internal": D("-100")}, D("0")
    )
    assert rates == {"savings_rate": 0.0, "savings_rate_with_debt": 0.0}
