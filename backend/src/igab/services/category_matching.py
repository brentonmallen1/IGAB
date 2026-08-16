"""Tolerant matching of AI-returned category names to real categories.

Models routinely "clean up" the names they were shown: decorations like the
"{$457}" funding reminders some users keep in category names get stripped,
and an ambiguous name may come back group-qualified ("Gifts (Household)").
Matching is tiered — exact first, then progressively more tolerant — and it
never guesses between two categories that remain ambiguous at the strictest
tier that matched anything.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# "{...}" funding reminders and "*" markers are decoration, not identity.
_DECORATION_RE = re.compile(r"\{[^}]*\}")

Candidate = tuple[str, str | None]  # (category name, group name or None)


def normalize_category_name(name: str) -> str:
    """Matching key for a category name: decorations stripped, whitespace
    collapsed, casefolded."""
    text = _DECORATION_RE.sub(" ", name).replace("*", " ")
    return " ".join(text.split()).casefold()


def match_category(raw: str | None, candidates: Sequence[Candidate]) -> int | None:
    """Index of the candidate a model-returned name refers to, or None.

    Tiers, strictest first; the first tier with hits decides:
    exact name → exact "name (group)" → normalized name → normalized
    "name (group)". More than one hit at that tier (the same name in
    several groups, unqualified) is ambiguous — never guess.
    """
    if not raw or not raw.strip():
        return None
    text = " ".join(raw.split())

    def exact(value: str, target: str) -> bool:
        return value.casefold() == target.casefold()

    def normalized(value: str, target: str) -> bool:
        return normalize_category_name(value) == normalize_category_name(target)

    tiers = (
        lambda name, group: exact(text, name),
        lambda name, group: group is not None and exact(text, f"{name} ({group})"),
        lambda name, group: normalized(text, name),
        lambda name, group: group is not None and normalized(text, f"{name} ({group})"),
    )
    for tier in tiers:
        hits = [i for i, (name, group) in enumerate(candidates) if tier(name, group)]
        if len(hits) == 1:
            return hits[0]
        if hits:
            return None
    return None


def canonical_label(index: int, candidates: Sequence[Candidate]) -> str:
    """The unambiguous label for a matched candidate: the real category name,
    group-qualified only when that name repeats across groups. This is what
    downstream resolution and the review UI should carry."""
    name, group = candidates[index]
    duplicated = sum(1 for n, _ in candidates if n.casefold() == name.casefold()) > 1
    return f"{name} ({group})" if duplicated and group else name
