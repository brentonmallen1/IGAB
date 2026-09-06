"""What a monthly debt payment is made of, and whether the ledger agrees.

Every payoff figure in this app runs on principal and interest. A mortgage
bill is usually P&I plus escrowed tax, insurance and PMI, and the escrow half
had nowhere to be recorded — so the app could not show the bill actually paid,
could not say that transfers exceeded the stated payment, and could not notice
mortgage insurance outliving the equity that justified it.
"""

from decimal import Decimal

import pytest

from igab.domain.payment_composition import (
    MAX_COMPONENTS,
    CompositionError,
    PaymentComponent,
    check_composition,
    components_total,
    full_monthly_payment,
    parse_components,
)


def D(v: str) -> Decimal:
    return Decimal(v)


def component(kind: str = "tax", amount: str = "410.00", label: str | None = None) -> dict:
    body = {"kind": kind, "amount": amount}
    if label is not None:
        body["label"] = label
    return body


class TestParsing:
    def test_no_composition_is_the_ordinary_case(self):
        # Every debt that is not an escrowed mortgage.
        assert parse_components(None) == []
        assert parse_components([]) == []

    def test_a_kind_carries_a_default_label_so_a_row_is_never_nameless(self):
        [parsed] = parse_components([component()])
        assert parsed.kind == "tax"
        assert parsed.label == "Property tax"
        assert parsed.amount == D("410.00")

    def test_the_users_own_wording_wins(self):
        [parsed] = parse_components([component(label="County + city tax")])
        assert parsed.label == "County + city tax"

    def test_amounts_are_quantized_to_cents(self):
        # The app's money convention, banker's rounding — see quantize_cents.
        [parsed] = parse_components([component(amount="410.007")])
        assert parsed.amount == D("410.01")
        [tie] = parse_components([component(amount="410.005")])
        assert tie.amount == D("410.00")

    @pytest.mark.parametrize(
        "bad",
        [
            "not a list",
            [{"kind": "spaceship", "amount": "10"}],
            [{"kind": "tax", "amount": "not money"}],
            [{"kind": "tax", "amount": "-1"}],
            ["not an object"],
        ],
    )
    def test_it_refuses_rather_than_repairs(self, bad):
        """A composition is a figure the user reads back off a statement to
        check the app agrees with it. Silently dropping a row would produce a
        total that matches nothing they can see."""
        with pytest.raises(CompositionError):
            parse_components(bad)

    def test_a_runaway_list_is_refused(self):
        with pytest.raises(CompositionError):
            parse_components([component()] * (MAX_COMPONENTS + 1))


class TestTheTotals:
    def test_the_bill_is_p_and_i_plus_the_parts(self):
        components = parse_components(
            [component("tax", "410.00"), component("insurance", "95.00"), component("pmi", "42.80")]
        )
        assert components_total(components) == D("547.80")
        assert full_monthly_payment(D("1896.20"), components) == D("2444.00")

    def test_no_p_and_i_means_no_total_rather_than_a_partial_one(self):
        """A total built on a missing half is a smaller number presented as a
        complete one — the exact failure this module exists to stop."""
        assert full_monthly_payment(None, parse_components([component()])) is None

    def test_a_debt_with_no_composition_totals_its_own_payment(self):
        assert full_monthly_payment(D("275.00"), []) == D("275.00")
        assert components_total([]) == D("0")


class TestDoesTheLedgerAgree:
    """The two readings mean different things and the app cannot tell which
    it is looking at. Transferring the WHOLE bill into the mortgage moves the
    balance by the escrow as well as the principal, so the debt appears to
    shrink faster than it does."""

    PI = D("1896.20")
    ESCROW = [
        PaymentComponent("tax", "Property tax", D("410.00")),
        PaymentComponent("insurance", "Insurance", D("95.00")),
        PaymentComponent("pmi", "PMI", D("42.80")),
    ]

    def test_paying_only_p_and_i_is_the_healthy_shape(self):
        # Escrow goes wherever escrow goes; the ledger means what the schedule
        # assumes it means.
        check = check_composition(self.PI, self.ESCROW, D("1896.20"))
        assert check.verdict == "matches_pi"

    def test_paying_the_whole_bill_into_the_loan_is_named(self):
        check = check_composition(self.PI, self.ESCROW, D("2444.00"))
        assert check.verdict == "matches_full"
        assert check.gap == D("547.80")

    def test_an_unexplained_excess_is_the_one_worth_asking_about(self):
        """Nobody can act on this without being told what the field is for,
        which is why the caller pairs the number with the advice."""
        check = check_composition(self.PI, [], D("2444.00"))
        assert check.verdict == "undeclared_gap"
        assert check.gap == D("547.80")

    def test_a_declared_composition_that_does_not_explain_the_gap_still_asks(self):
        check = check_composition(
            self.PI, [PaymentComponent("tax", "Tax", D("10.00"))], D("2444.00")
        )
        assert check.verdict == "undeclared_gap"

    def test_rounding_does_not_trip_it(self):
        # Escrow moves annually and people round their transfers; a note that
        # fires on a cent is a note people learn to skip.
        assert check_composition(self.PI, self.ESCROW, D("2444.01")).verdict == "matches_full"
        assert check_composition(self.PI, [], D("1896.21")).verdict == "matches_pi"

    def test_paying_under_p_and_i_is_not_a_composition_problem(self):
        """It has its own warning elsewhere — the payoff pill says the
        payments will not clear the debt."""
        assert check_composition(self.PI, [], D("900.00")).verdict == "unknown"

    def test_nothing_to_compare_says_nothing(self):
        assert check_composition(None, [], D("2444.00")).verdict == "unknown"
        assert check_composition(self.PI, [], None).verdict == "unknown"
