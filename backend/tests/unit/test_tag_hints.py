"""The tag hint table: what the importer writes vs what the review proposes.

The distinction is the whole point of the module, so it is pinned by name. A
hint that quietly gains `applied_on_import=True` starts writing a
classification override for every future import, which no other test would
catch.
"""

import pytest

from igab.domain.tag_hints import (
    DERIVED_KEYS,
    TAG_HINTS,
    TagSuggestion,
    suggest_review_tags,
    suggest_system_tag,
)


class TestWhatTheImporterApplies:
    def test_only_savings_and_long_term_expense_are_ever_written(self):
        applied = {h.system_key for h in TAG_HINTS if h.applied_on_import}
        assert applied == {"savings", "long_term_expense"}

    @pytest.mark.parametrize(
        ("category", "group", "expected"),
        [
            ("Savings", "Goals", "savings"),
            ("Emergency Fund", "Goals", "savings"),
            ("Rainy Day", "Goals", "savings"),
            ("Car Repairs", "True Expenses", "long_term_expense"),
            ("Sinking Fund", "Whatever", "long_term_expense"),
            ("Long-Term Care", "Whatever", "long_term_expense"),
        ],
    )
    def test_applied_hints_match(self, category, group, expected):
        assert suggest_system_tag(category, group).system_key == expected

    def test_the_categorys_own_name_wins_over_its_groups(self):
        # The documented rule: a "Vacation" in "True Expenses" is a long-term
        # expense, but a "Savings" in that same group is savings.
        assert suggest_system_tag("Savings", "True Expenses").system_key == "savings"
        assert suggest_system_tag("Vacation", "True Expenses").system_key == "long_term_expense"

    @pytest.mark.parametrize(
        ("category", "group"),
        [
            ("Groceries", "Everyday"),
            ("Rent", "Bills"),
            ("Amazon Prime", "Monthly"),
            ("Car Loan Payment", "Debt"),
        ],
    )
    def test_proposed_only_keys_are_never_written(self, category, group):
        """The regression that would turn a proposal into a silent write."""
        assert suggest_system_tag(category, group) is None


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
        ],
    )
    def test_proposes_the_keys_the_importer_never_assigns(self, category, group, expected):
        assert expected in {s.system_key for s in suggest_review_tags(category, group)}

    def test_every_proposed_key_has_at_least_one_case(self):
        """A hint nothing can match is a hint that does not exist."""
        proposed = {h.system_key for h in TAG_HINTS if not h.applied_on_import}
        assert proposed == {"subscription", "essential", "debt_principal"}

    def test_a_category_can_be_offered_more_than_one(self):
        # Real case from the dev database: tagged Long-term expense by the
        # import, but plainly a subscription. The review shows both rather
        # than picking for the user.
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
        assert suggest_system_tag(name, "Group").system_key == "savings"

    def test_electric_finds_electricity(self):
        offered = {s.system_key: s.matched_on for s in suggest_review_tags("Electricity", "Bills")}
        assert offered["essential"] == "Electricity"

    @pytest.mark.parametrize("name", ["Parents' Gifts", "Parent Care", "Different Things"])
    def test_a_fragment_does_not_match_mid_word(self, name):
        assert suggest_review_tags(name, "Family") == []
