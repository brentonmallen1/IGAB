"""Account-type guessing for YNAB imports.

Why this matters more than it looks: the mapping UI pre-fills every row with
this guess, and `to_be_assigned` is

    total_account_balance - total_category_balance - assigned_in_future

so an account wrongly marked ON budget silently corrupts every budget number.
A real 47-account export put a $1.2M house and a -$710K mortgage inside the
budget because neither name contained a recognised keyword. The safety property
below (`test_tracked_things_are_never_on_budget`) is the one that must hold.
"""

from decimal import Decimal

import pytest

from igab.api.v1.imports import suggest_account_type

POS = Decimal("1000")
NEG = Decimal("-1000")


class TestRecognisedTypes:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Cedar Grove Property Loan", "loan"),
            ("Vehicle A Loan", "loan"),
            ("Sallie Mae Student", "loan"),
            ("Meridian Visa", "credit_card"),
            ("Northgate Amex", "credit_card"),
            ("Redwood CC", "credit_card"),
            ("Discover Card", "credit_card"),
            ("Beacon Hill 401k", "investment"),
            ("Fairview Brokerage", "investment"),
            ("Fairview Roth", "investment"),
            ("Silverleaf Rollover IRA", "investment"),
            ("Employer A ESPP Stock", "investment"),
            ("Employer A Stock", "investment"),
            ("Employer B Co-invest", "investment"),
            ("Stonebridge HSA Investment", "investment"),
            ("Crypto", "other_asset"),
            ("TreasuryDirect", "other_asset"),
            ("Union Ridge Checking", "checking"),
            ("Cascade Point HYSA", "savings"),
            ("Harborstone MM", "savings"),
            ("Harborstone Savings", "savings"),
            ("Cash", "cash"),
        ],
    )
    def test_type_is_recognised_confidently(self, name, expected):
        account_type, _, needs_review = suggest_account_type(name, POS)
        assert account_type == expected
        assert needs_review is False

    def test_explicit_debt_outranks_the_thing_it_is_secured_against(self):
        # "Cedar Grove Property Loan" contains both "property" and "loan".
        assert suggest_account_type("Cedar Grove Property Loan", NEG)[0] == "loan"
        assert suggest_account_type("Vehicle A Loan", NEG)[0] == "loan"


class TestTrackedThings:
    """Names describing something owned or owed. The name alone cannot say
    which side it falls on, so the register's sign decides — but either way the
    account must stay OFF budget."""

    @pytest.mark.parametrize(
        "name",
        [
            "Birchwood Property Ferry",
            "Birchwood Property Ferry House",
            "Cedar Grove Property Road",
            "Vehicle A",
            "Vehicle B",
            "Lakeside Trust MM - tracked",
            "Lakeside Trust S - tracked",
            "Beach Condo",
            "Boat",
        ],
    )
    def test_tracked_things_are_never_on_budget(self, name):
        for balance in (POS, NEG, Decimal("0")):
            _, on_budget, _ = suggest_account_type(name, balance)
            assert on_budget is False, f"{name} @ {balance} leaked into the budget"

    def test_sign_picks_asset_vs_liability(self):
        assert suggest_account_type("Birchwood Property Ferry House", POS)[0] == "other_asset"
        assert suggest_account_type("Birchwood Property Ferry", NEG)[0] == "other_liability"

    def test_ambiguous_side_is_flagged_for_review(self):
        assert suggest_account_type("Vehicle A", POS)[2] is True

    def test_explicit_tracking_marker_outranks_a_type_keyword(self):
        # "MM" would otherwise read as a money-market savings account.
        account_type, on_budget, _ = suggest_account_type("Lakeside Trust MM - tracked", POS)
        assert on_budget is False
        assert account_type == "other_asset"


class TestUnrecognisedNames:
    @pytest.mark.parametrize(
        "name", ["Harborstone", "Redwood", "Apple Wallet", "Discovery Fund", "First Federal"]
    )
    def test_unknown_names_are_flagged_for_review(self, name):
        account_type, on_budget, needs_review = suggest_account_type(name, POS)
        assert (account_type, on_budget) == ("checking", True)
        assert needs_review is True, "an unrecognised name must not import silently"


class TestFalsePositives:
    """Short keywords must match on token boundaries only. These are real
    bank-name shapes that a substring match would misfile."""

    @pytest.mark.parametrize(
        "name,would_have_matched",
        [
            ("Admiral Federal", "ira"),
            ("Account Services", "cc"),
            ("Summit Bank", "mm"),
            ("Carnival Rewards", "car"),
            ("Cashmere Valley", "cash"),
            ("Cleveland Trust", "land"),
            ("Discovery Fund", "discover"),
            ("Autonomy Bank", "auto"),
        ],
    )
    def test_short_keyword_does_not_fire_inside_a_longer_word(self, name, would_have_matched):
        account_type, _, needs_review = suggest_account_type(name, POS)
        assert (account_type, needs_review) == ("checking", True), (
            f"{name!r} misfiled — {would_have_matched!r} matched as a substring"
        )

    def test_concatenated_names_still_resolve(self):
        assert suggest_account_type("TreasuryDirect", POS)[0] == "other_asset"
        assert suggest_account_type("SavingsPlus", POS)[0] == "savings"


class TestBalanceIsOptional:
    def test_missing_balance_defaults_to_asset_side(self):
        account_type, on_budget, _ = suggest_account_type("Vehicle A")
        assert (account_type, on_budget) == ("other_asset", False)
