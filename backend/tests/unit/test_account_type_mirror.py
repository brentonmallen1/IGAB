"""The frontend's built-in account types must match the backend seed.

`frontend/src/constants/accountTypes.ts` is the fallback rendered at the YNAB
import mapping step — before a budget, and therefore its type registry, exists.
That is the highest-stakes moment for this copy: the mapping decides whether an
account lands on budget, and an on-budget mistake corrupts `to_be_assigned` by
construction.

Its header says "keep the two in step", which is exactly the kind of promise a
comment cannot keep. When the backend descriptions gained the savings/debt
rules, the mirror kept the old text — so the modal explaining the choice showed
none of the guidance that made the choice consequential, while the post-import
panel showed the new wording for the same type.
"""

import json
import re
from pathlib import Path

import pytest

from igab.domain.account_types import BUILTIN_ACCOUNT_TYPES

MIRROR = (
    Path(__file__).resolve().parents[3] / "frontend" / "src" / "constants" / "accountTypes.ts"
)

#: The api container mounts only `backend/`, so `just test-backend` cannot see
#: the mirror. `just ci` — and therefore GitHub CI, which gates merges — runs
#: outside Docker from the repo root and does. Skipping is honest about that;
#: failing would make a green Docker run impossible for a reason unrelated to
#: the code under test.
needs_frontend_tree = pytest.mark.skipif(
    not MIRROR.exists(), reason="frontend tree not mounted (Docker); enforced by `just ci`"
)


def _parse_mirror() -> dict[str, dict]:
    """Pull the object literals out of the TS constant.

    A parser rather than a build step: the file is hand-edited and human-read,
    and generating it would trade a drift problem for a codegen one.
    """
    source = MIRROR.read_text()
    body = source[source.index("BUILTIN_ACCOUNT_TYPES") : source.rindex("\n]")]
    entries: dict[str, dict] = {}
    for block in re.findall(r"\{(.*?)\n  \}", body, re.S):
        key = re.search(r"key:\s*'([^']*)'", block).group(1)
        label = re.search(r"label:\s*'([^']*)'", block).group(1)
        classification = re.search(r"classification:\s*'([^']*)'", block).group(1)
        on_budget = re.search(r"default_on_budget:\s*(true|false)", block).group(1)
        # Description may be a single quoted string or several joined by `+`,
        # and is the last field, so it may end the block without a newline.
        raw = block[block.index("description:") :]
        description = "".join(re.findall(r"'((?:[^'\\]|\\.)*)'", raw)).replace("\\'", "'")
        entries[key] = {
            "label": label,
            "classification": classification,
            "default_on_budget": on_budget == "true",
            "description": description,
        }
    return entries


@needs_frontend_tree
def test_mirror_file_exists_where_the_comment_says():
    assert MIRROR.exists(), MIRROR


@needs_frontend_tree
def test_the_same_types_in_the_same_order():
    mirror = _parse_mirror()
    assert list(mirror) == [t.key for t in BUILTIN_ACCOUNT_TYPES]


@needs_frontend_tree
@pytest.mark.parametrize("builtin", BUILTIN_ACCOUNT_TYPES, ids=lambda t: t.key)
def test_each_type_matches_the_backend_seed(builtin):
    entry = _parse_mirror()[builtin.key]
    assert entry["label"] == builtin.label
    assert entry["classification"] == builtin.classification
    assert entry["default_on_budget"] == builtin.default_on_budget
    assert entry["description"] == builtin.description, (
        f"{builtin.key}: mirror copy has drifted from the backend seed.\n"
        f"  backend: {builtin.description}\n"
        f"  mirror:  {entry['description']}"
    )


@needs_frontend_tree
def test_the_parser_would_notice_a_difference():
    """Guards the guard: a parser that silently returned nothing would make
    every assertion above vacuous."""
    mirror = _parse_mirror()
    assert len(mirror) == len(BUILTIN_ACCOUNT_TYPES) > 0
    assert all(e["description"] for e in mirror.values())
