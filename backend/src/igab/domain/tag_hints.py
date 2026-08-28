"""What a category's name says about how its money should be classified.

Pure: no session, no budget, no tag rows — just names in, system keys out, so
every fragment is a one-line test.

Two callers with different consequences, and the difference is the whole point
of this module:

- The YNAB importer **writes** a tag for a fresh category (`suggest_system_tag`).
  A system tag overrides classification outright (see `domain.activity_class`),
  so a wrong guess here silently moves burn rate, savings rate and the spending
  charts. That is why only the two unmistakable keys are applied.
- The import review **proposes** the rest (`suggest_review_tags`), unchecked,
  for a person to accept. A proposal that misses costs nothing; one that is
  clever and wrong costs trust.

One table serves both, flagged. Two lists would drift, and the drift would be
invisible: the review would stop offering what the importer had started
applying, or worse, the reverse.
"""

import re
from dataclasses import dataclass
from functools import cache

#: Never proposed. `wishlist` is derived from the wish -> envelope link by
#: `guide.wishlist_service`, and re-derived on the next wishlist write, so
#: offering it would be offering a choice the app immediately overrules.
DERIVED_KEYS = frozenset({"wishlist"})


@dataclass(frozen=True)
class TagSuggestion:
    """A key these names point at, and the name that pointed at it.

    Both callers need the "why": the importer records it so the review can
    show its working, and the review renders it. A suggestion a person cannot
    check is one they have to take on faith.
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
    #: True  -> the importer writes this tag when it matches.
    #: False -> only ever offered in the review, never written by the import.
    applied_on_import: bool


#: Kept short and obvious rather than clever, in both halves. The applied half
#: is unchanged from when it lived in `repositories.tag_repo`; widening it is
#: how proposals would turn into silent writes.
TAG_HINTS: tuple[TagHint, ...] = (
    TagHint("savings", ("saving", "emergency fund", "rainy day", "nest egg"), True),
    TagHint(
        "long_term_expense",
        ("true expense", "long term", "long-term", "sinking fund"),
        True,
    ),
    # Proposed only, from here down. These are the three the importer has never
    # assigned — a real 100-category import produced zero of each — which is
    # why an imported budget's Essentials report is empty and its emergency-fund
    # target is measured against all spending instead.
    TagHint(
        "subscription",
        ("subscription", "streaming", "membership", "prime", "netflix", "spotify"),
        False,
    ),
    TagHint(
        "essential",
        ("rent", "mortgage", "groceries", "electric", "utilities", "insurance"),
        False,
    ),
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


def suggest_system_tag(category_name: str, group_name: str) -> TagSuggestion | None:
    """The one system tag an imported category's names point at, if any.

    The category's own name wins: a "Vacation" category inside a "True
    Expenses" group is a long-term expense, but a "Savings" category in that
    same group is savings. That precedence is why this cannot just be
    `suggest_review_tags(...)[0]` — the two answer different questions, one
    picking a single winner and one listing every candidate.

    Applied hints only. The importer must never start writing what the review
    exists to propose.
    """
    for haystack in (category_name, group_name):
        for hint in TAG_HINTS:
            if not hint.applied_on_import:
                continue
            if _pattern(hint.fragments).search(haystack.lower()):
                return TagSuggestion(system_key=hint.system_key, matched_on=haystack)
    return None


def suggest_review_tags(category_name: str, group_name: str) -> list[TagSuggestion]:
    """Every system key these names point at, in `TAG_HINTS` order.

    A category can be offered more than one — "Car Insurance" is plausibly
    both essential and a long-term expense, and picking one for the user would
    be guessing at the thing they opened the review to decide.
    """
    out: list[TagSuggestion] = []
    for hint in TAG_HINTS:
        if hint.system_key in DERIVED_KEYS:
            continue
        matched = _matched_name(hint, category_name, group_name)
        if matched is not None:
            out.append(TagSuggestion(system_key=hint.system_key, matched_on=matched))
    return out
