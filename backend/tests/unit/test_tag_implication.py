"""Which tag implies which, stated once (`domain.tag_implication`).

It was three statements, and each one knew a different part of it:

- `tag_hints.IMPLIED_TAGS` — Emergency fund → Savings, and nothing else, so the
  import review offered Cost of living to an Essential category;
- `category_filters.SAVINGS_CATEGORY_KEYS` — Emergency fund → Savings again,
  written out as a pair of keys;
- `activity_class.TIER_TAG_KEYS` — Essential → Cost of living, as the nesting of
  two literal key tuples.

These pin that all three now derive from `IMPLIES`, and what the relation says.
"""

import pytest

from igab.domain.activity_class import TIER_TAG_KEYS, NecessityTier
from igab.domain.tag_implication import (
    COST_OF_LIVING_KEY,
    EMERGENCY_FUND_KEY,
    ESSENTIAL_KEY,
    IMPLICATION_PAIRS,
    IMPLIES,
    SAVINGS_KEY,
    implied_by,
    implying,
    keys_counting_as,
)
from igab.repositories.category_filters import SAVINGS_CATEGORY_KEYS
from igab.repositories.tag_repo import SYSTEM_TAGS


class TestTheRelation:
    def test_each_implication_is_written_once(self):
        assert IMPLICATION_PAIRS == (
            (EMERGENCY_FUND_KEY, SAVINGS_KEY),
            (ESSENTIAL_KEY, COST_OF_LIVING_KEY),
        )

    def test_the_keys_are_the_seeded_system_tags(self):
        seeded = {key for key, _name, _color in SYSTEM_TAGS}
        for implier, implied in IMPLICATION_PAIRS:
            assert {implier, implied} <= seeded

    @pytest.mark.parametrize(
        ("keys", "expected"),
        [
            ([EMERGENCY_FUND_KEY], {SAVINGS_KEY}),
            ([ESSENTIAL_KEY], {COST_OF_LIVING_KEY}),
            ([EMERGENCY_FUND_KEY, ESSENTIAL_KEY], {SAVINGS_KEY, COST_OF_LIVING_KEY}),
            # One way only: most savings is not a fund for surprises, and a
            # subscription is cost of living without being essential.
            ([SAVINGS_KEY], set()),
            ([COST_OF_LIVING_KEY], set()),
            (["subscription", "long_term_expense"], set()),
            ([], set()),
        ],
    )
    def test_implied_by(self, keys, expected):
        assert implied_by(keys) == expected

    def test_implying(self):
        assert implying(SAVINGS_KEY) == (EMERGENCY_FUND_KEY,)
        assert implying(COST_OF_LIVING_KEY) == (ESSENTIAL_KEY,)
        assert implying(ESSENTIAL_KEY) == ()
        assert implying(EMERGENCY_FUND_KEY) == ()

    def test_no_key_implies_itself(self):
        """A cycle would list a key among its own impliers — a checklist row
        locked by the tag it is the checklist of."""
        for key in IMPLIES:
            assert key not in implied_by([key])

    def test_the_key_itself_comes_first(self):
        assert keys_counting_as(SAVINGS_KEY) == (SAVINGS_KEY, EMERGENCY_FUND_KEY)
        assert keys_counting_as("subscription") == ("subscription",)


class TestEveryReaderDerivesFromIt:
    def test_savings_categories(self):
        assert SAVINGS_CATEGORY_KEYS == keys_counting_as(SAVINGS_KEY)
        assert set(SAVINGS_CATEGORY_KEYS) == {SAVINGS_KEY, EMERGENCY_FUND_KEY}

    def test_necessity_tiers(self):
        assert TIER_TAG_KEYS[NecessityTier.ESSENTIAL] == (ESSENTIAL_KEY,)
        assert set(TIER_TAG_KEYS[NecessityTier.COST_OF_LIVING]) == {
            ESSENTIAL_KEY,
            COST_OF_LIVING_KEY,
        }

    def test_an_implication_nests_the_tiers(self):
        """Essentials ⊆ Cost of Living because Essential implies Cost of
        living, not because two tuples happen to agree."""
        for implier, implied in IMPLICATION_PAIRS:
            assert set(keys_counting_as(implier)) <= set(keys_counting_as(implied))
