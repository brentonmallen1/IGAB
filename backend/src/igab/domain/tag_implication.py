"""Which system tag another one already means — the one statement of it.

An Emergency fund category IS a savings category: an emergency fund is money
set aside. An Essential category IS a cost-of-living category: what a household
could not cut is, by definition, not discretionary. Each of those is written
once, in `IMPLIES`, and everything that asks "which tags make a category count
as tagged X" derives its answer from it:

- `category_filters.SAVINGS_CATEGORY_KEYS` — what makes a category a savings
  category (the classifier's rule 1, `SAVINGS_ROLE`, the Savings report);
- `activity_class.TIER_TAG_KEYS` — which tags each necessity tier reads;
- `tag_hints.suggest_review_tags` — the import review never offers a tag a
  held or offered one already implies;
- `category_filters.implying_tag_name` — a tag's checklist shows an implied
  row ticked and locked, and its "N categories" count includes it.

It used to be three statements. Emergency fund → Savings was written twice
(`IMPLIED_TAGS` in tag_hints and `SAVINGS_CATEGORY_KEYS`), Essential → Cost of
living once, as the nesting inside `TIER_TAG_KEYS`, and the suggestion table
did not know it: the import review offered Cost of living to a category already
tagged Essential, and the Cost of living checklist drew every Essential
category unticked while the report counted it.

**An implication, never an auto-add.** Nothing writes the implied tag. A
category tagged Essential carries one tag and counts under two; tagging it Cost
of living as well would change nothing but its tag list.

Pure: keys in, keys out.
"""

from collections.abc import Iterable, Mapping

#: The system tag that makes a category a savings category.
SAVINGS_KEY = "savings"
#: The emergency-fund tag. It implies Savings.
EMERGENCY_FUND_KEY = "emergency_fund"
#: What a household could not cut — the lean necessity tier.
ESSENTIAL_KEY = "essential"
#: Committed but sheddable — the wide necessity tier.
COST_OF_LIVING_KEY = "cost_of_living"

#: X → the keys X implies: every category tagged X counts as tagged each of
#: them. One way only — most savings is not a fund for surprises, and a
#: subscription is cost of living without being essential.
IMPLIES: Mapping[str, tuple[str, ...]] = {
    EMERGENCY_FUND_KEY: (SAVINGS_KEY,),
    ESSENTIAL_KEY: (COST_OF_LIVING_KEY,),
}

#: The relation as (implying key, implied key) pairs — the shape a SQL
#: predicate matches a tag row's key against (`category_filters`).
IMPLICATION_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (implier, implied) for implier, targets in IMPLIES.items() for implied in targets
)


def implied_by(keys: Iterable[str]) -> frozenset[str]:
    """Every key these keys imply, transitively — never the keys themselves
    unless something among them implies them."""
    out: set[str] = set()
    frontier = list(keys)
    while frontier:
        for implied in IMPLIES.get(frontier.pop(), ()):
            if implied not in out:
                out.add(implied)
                frontier.append(implied)
    return frozenset(out)


def implying(key: str) -> tuple[str, ...]:
    """Every key that implies `key`, transitively, in `IMPLIES` order."""
    return tuple(k for k in IMPLIES if key in implied_by([k]))


def keys_counting_as(key: str) -> tuple[str, ...]:
    """The keys whose tag makes a category count as tagged `key`: the key
    itself first, then every key that implies it."""
    return (key, *implying(key))
