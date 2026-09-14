"""The tag hint table: what the import review proposes — and that nothing is
written from a name.

The importer used to write Savings from names like "Emergency Fund". A hint
that quietly gains `applied_on_import=True` would be a proposal turned into a
silent classification override, so the empty set is pinned by name.
"""

import pytest

from igab.domain.tag_hints import (
    DERIVED_KEYS,
    IMPLIED_TAGS,
    TAG_HINTS,
    TagSuggestion,
    implied_by,
    suggest_review_tags,
)


class TestNothingIsWrittenFromAName:
    def test_no_hint_is_applied_on_import(self):
        assert {h.system_key for h in TAG_HINTS if h.applied_on_import} == set()

    @pytest.mark.parametrize(
        ("category", "group"),
        [
            # YNAB's default template ships a "True Expenses" group, and the
            # hint matches a GROUP name as well as a category's — so every
            # ordinary category inside it used to acquire the tag on import.
            ("Car Repairs", "True Expenses"),
            ("Sinking Fund", "Whatever"),
        ],
    )
    def test_long_term_expense_is_offered(self, category, group):
        keys = {t.system_key for t in suggest_review_tags(category, group)}
        assert "long_term_expense" in keys


class TestTheEmergencyFundHint:
    @pytest.mark.parametrize(
        ("category", "matched_on"),
        [("Emergency Fund", "Emergency Fund"), ("Rainy Day", "Rainy Day"), ("Buffer", "Buffer")],
    )
    def test_emergency_names_are_offered_emergency_fund(self, category, matched_on):
        assert suggest_review_tags(category, "Goals") == [
            TagSuggestion("emergency_fund", matched_on)
        ]

    def test_savings_names_are_offered_savings(self):
        assert suggest_review_tags("Savings", "Goals") == [TagSuggestion("savings", "Savings")]
        assert suggest_review_tags("Nest Egg", "Goals") == [TagSuggestion("savings", "Nest Egg")]

    def test_a_name_offered_both_is_offered_emergency_fund_alone(self):
        """Emergency fund implies Savings, so offering both would be offering
        a second copy of one fact."""
        assert suggest_review_tags("Rainy Day Savings", "Goals") == [
            TagSuggestion("emergency_fund", "Rainy Day Savings")
        ]

    def test_an_emergency_fund_category_is_never_offered_savings(self):
        assert suggest_review_tags("Car Savings", "Goals", held=["emergency_fund"]) == []

    def test_a_held_key_is_not_offered_again(self):
        assert suggest_review_tags("Savings", "Goals", held=["savings"]) == []

    def test_the_implication_is_one_way(self):
        """Savings does not imply Emergency fund: most savings is not a fund
        for surprises."""
        assert implied_by(["emergency_fund"]) == {"savings"}
        assert implied_by(["savings"]) == frozenset()
        assert suggest_review_tags("Emergency Fund", "Goals", held=["savings"]) == [
            TagSuggestion("emergency_fund", "Emergency Fund")
        ]

    def test_every_implied_key_is_a_hinted_key(self):
        hinted = {h.system_key for h in TAG_HINTS}
        for key, implied in IMPLIED_TAGS.items():
            assert key in hinted
            assert set(implied) <= hinted


class TestWhatTheReviewProposes:
    @pytest.mark.parametrize(
        ("category", "group", "expected"),
        [
            ("Groceries", "Everyday", "essential"),
            ("Rent", "Bills", "essential"),
            ("Electricity", "Bills", "essential"),
            ("Car Insurance", "Bills", "essential"),
            ("Amazon Prime", "Monthly", "subscription"),
            ("Streaming", "Fun", "subscription"),
            ("Car Loan Payment", "Debt", "debt_principal"),
            ("Gym Membership", "Fun", "cost_of_living"),
            ("Storage Unit", "Bills", "cost_of_living"),
            ("Home Maintenance", "Long Term", "cost_of_living"),
            # Subscription-shaped by brand name: offered both, not Subscription
            # alone. The wide tier's hint copied only half the fragments.
            ("Netflix", "Fun", "cost_of_living"),
            ("Spotify", "Fun", "cost_of_living"),
            ("Amazon Prime", "Monthly", "cost_of_living"),
        ],
    )
    def test_proposes_the_keys_the_importer_never_assigns(self, category, group, expected):
        assert expected in {s.system_key for s in suggest_review_tags(category, group)}

    def test_every_proposed_key_has_at_least_one_case(self):
        """A hint nothing can match is a hint that does not exist."""
        proposed = {h.system_key for h in TAG_HINTS if not h.applied_on_import}
        assert proposed == {
            "savings",
            "emergency_fund",
            "long_term_expense",
            "subscription",
            "essential",
            "cost_of_living",
            "debt_principal",
        }

    def test_a_category_can_be_offered_more_than_one(self):
        # Real case from the dev database: the import used to WRITE
        # Long-term expense here, on a category that is plainly a
        # subscription. Now both are offered and neither is written.
        offered = {
            s.system_key: s.matched_on
            for s in suggest_review_tags("Amazon Prime", "Long Term Expenses")
        }
        assert offered["long_term_expense"] == "Long Term Expenses"
        assert offered["subscription"] == "Amazon Prime"

    def test_it_says_which_name_matched(self):
        """A proposal a person cannot check is one they have to take on faith."""
        assert suggest_review_tags("Vacation", "True Expenses") == [
            TagSuggestion("long_term_expense", "True Expenses")
        ]
        assert suggest_review_tags("Groceries", "Everyday") == [
            TagSuggestion("essential", "Groceries")
        ]

    def test_wishlist_is_never_proposed(self):
        """Derived from the wish -> envelope link; the app would overrule it."""
        assert "wishlist" in DERIVED_KEYS
        offered = {s.system_key for s in suggest_review_tags("Wishlist", "Wishlist")}
        assert not (offered & DERIVED_KEYS)


class TestWordStartMatching:
    """Fragments match the start of a word, not any substring.

    Bare substrings are what would make "rent" match "Parents"; whole words are
    what would stop "saving" matching "Savings". Both halves are pinned here
    because a change to either breaks a real budget quietly.
    """

    @pytest.mark.parametrize("name", ["Savings", "Car Savings", "Savings Goals"])
    def test_a_fragment_matches_any_suffix(self, name):
        assert [t.system_key for t in suggest_review_tags(name, "Group")] == ["savings"]

    def test_electric_finds_electricity(self):
        offered = {s.system_key: s.matched_on for s in suggest_review_tags("Electricity", "Bills")}
        assert offered["essential"] == "Electricity"

    @pytest.mark.parametrize("name", ["Parents' Gifts", "Parent Care", "Different Things"])
    def test_a_fragment_does_not_match_mid_word(self, name):
        assert suggest_review_tags(name, "Family") == []


def test_every_subscription_shaped_name_is_offered_the_wide_tier_too():
    """The Cost of living hint is built from the Subscription hint's fragments,
    not a copy of some of them."""
    by_key = {h.system_key: set(h.fragments) for h in TAG_HINTS}
    assert by_key["subscription"] <= by_key["cost_of_living"]
