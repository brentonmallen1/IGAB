"""What a category's name suggests about how its money should be counted.

Pure: no session, no budget, no tag rows — just names in, system keys out, so
every fragment is a one-line test.

**Suggestions only.** The import review proposes these, unchecked, for a person
to accept (`suggest_review_tags`); nothing writes a tag from a name. The YNAB
importer used to write one — Savings, from names like "Emergency Fund" and
"Rainy Day" — and that tag overrides classification, so a wrong guess silently
moved burn rate and the savings rate. Once Savings grew a "sent out / kept here"
choice and the emergency fund became something chosen, not guessed, a name was
no longer enough to decide either, and the write path went
(`integrations/ynab/importer.py`). A proposal that misses costs nothing; one
that is clever and wrong costs trust.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from igab.domain.tag_implication import implied_by

#: Never proposed. `wishlist` is derived from the wish -> envelope link by
#: `guide.wishlist_service`, and re-derived on the next wishlist write, so
#: offering it would be offering a choice the app immediately overrules.
DERIVED_KEYS = frozenset({"wishlist"})


@dataclass(frozen=True)
class TagSuggestion:
    """A key these names point at, and the name that pointed at it.

    The review renders the "why": a suggestion a person cannot check is one
    they have to take on faith.
    """

    system_key: str
    matched_on: str


@dataclass(frozen=True)
class TagHint:
    system_key: str
    #: Lowercase fragments, matched at a WORD START against the category's
    #: name and its group's. Not whole words -- "saving" has to match
    #: "Savings" and "Car Savings". Not bare substrings either -- that is what
    #: would make "rent" match "Parents" and "Different".
    fragments: tuple[str, ...]
    #: Whether the importer writes this tag. False for every hint: served as
    #: `TagSuggestionOut.applied_on_import` so an old import's review still
    #: reads, and pinned empty by `test_tag_hints.py` — a hint that gains True
    #: would need a write path, which no longer exists.
    applied_on_import: bool


#: What "subscription-shaped" means, said once. Both the Subscription hint and
#: the wider Cost of living hint offer these: the wide tier's hint exists so a
#: subscription is offered the tier too. It copied half of them, so Netflix,
#: Spotify and Amazon Prime were offered Subscription but not Cost of living
#: while "Streaming" was offered both — the gap stayed empty for exactly the
#: categories the hint was written for.
_SUBSCRIPTION = ("subscription", "streaming", "membership", "prime", "netflix", "spotify")

#: Kept short and obvious rather than clever.
TAG_HINTS: tuple[TagHint, ...] = (
    # Savings no longer claims "emergency fund" or "rainy day": those name the
    # Emergency fund tag now, which implies Savings (`domain.tag_implication`).
    TagHint("savings", ("saving", "nest egg"), False),
    TagHint("emergency_fund", ("emergency", "rainy day", "buffer"), False),
    # `long_term_expense` was written on import until it stopped overriding
    # classification. Its fragments match a GROUP name as well as a category's,
    # and YNAB's default template ships a group called "True Expenses" — so
    # every ordinary category inside it, "Clothing" included, silently acquired
    # the tag on import. A tag whose remaining job is Savings-report membership
    # is far too weak a signal to write into a user's budget unasked; the
    # review can offer it and the household can say yes.
    TagHint(
        "long_term_expense",
        ("true expense", "long term", "long-term", "sinking fund"),
        False,
    ),
    # These three the importer has never assigned — a real 100-category import
    # produced zero of each — which is why an imported budget's Essentials
    # report is empty and its emergency-fund target is measured against all
    # spending instead.
    TagHint("subscription", _SUBSCRIPTION, False),
    TagHint(
        "essential",
        ("rent", "mortgage", "groceries", "electric", "utilities", "insurance"),
        False,
    ),
    # The wider tier. A real 100-category import produced zero `essential`
    # tags, which is why an imported budget's Essentials report is empty — and
    # a tier that a subscription- or membership-shaped category can be OFFERED
    # is the only realistic path to a non-empty gap on an imported budget.
    TagHint("cost_of_living", (*_SUBSCRIPTION, "gym", "storage", "maintenance"), False),
    TagHint("debt_principal", ("loan payment", "debt payment", "principal"), False),
)


@cache
def _pattern(fragments: tuple[str, ...]) -> re.Pattern[str]:
    """One word-start alternation per hint.

    `\b` before each fragment and nothing after, so a fragment matches the
    beginning of a word and any suffix: "saving" finds "Savings", "electric"
    finds "Electricity", and "rent" finds "Rent" without finding "Parents".
    """
    return re.compile("|".join(r"\b" + re.escape(f) for f in fragments))


def _matched_name(hint: TagHint, category_name: str, group_name: str) -> str | None:
    """The name that triggered this hint, or None.

    The name rather than a bool because the review shows its working: a
    proposal a person cannot check is one they have to take on faith.
    """
    for haystack in (category_name, group_name):
        if _pattern(hint.fragments).search(haystack.lower()):
            return haystack
    return None


def suggest_review_tags(
    category_name: str, group_name: str, held: Iterable[str] = ()
) -> list[TagSuggestion]:
    """Every system key these names point at that the category does not
    already carry, in `TAG_HINTS` order.

    `held` is the category's system keys. A key a held or suggested tag
    implies is not offered (`domain.tag_implication`): offering it would be
    offering a second copy of a fact the category already carries, and
    accepting it would change nothing but the tag list. An Emergency fund
    category is never offered Savings, an Essential one never Cost of living,
    and "Rainy Day Savings" is offered Emergency fund alone.

    A category can be offered more than one — "Car Insurance" is plausibly
    both essential and a long-term expense, and picking one for the user would
    be guessing at the thing they opened the review to decide.

    That pair used to defeat itself: `long_term_expense` classified the row
    SAVINGS, and the essentials family counts SPENDING and DEBT_PRINCIPAL, so
    accepting both put the category in the Essentials report's "tagged and
    still not counted" note. Since the tag stopped overriding classification
    it is the right answer for a sinking fund against a bill you cannot cut,
    and the sample budget now demonstrates the combination instead of avoiding
    it.
    """
    out: list[TagSuggestion] = []
    for hint in TAG_HINTS:
        if hint.system_key in DERIVED_KEYS:
            continue
        matched = _matched_name(hint, category_name, group_name)
        if matched is not None:
            out.append(TagSuggestion(system_key=hint.system_key, matched_on=matched))
    held_keys = set(held)
    implied = implied_by(held_keys | {x.system_key for x in out})
    return [x for x in out if x.system_key not in held_keys and x.system_key not in implied]
