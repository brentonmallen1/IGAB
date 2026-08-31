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

import re
from pathlib import Path

import pytest

from igab.domain.account_types import BUILTIN_ACCOUNT_TYPES

MIRROR = Path(__file__).resolve().parents[3] / "frontend" / "src" / "constants" / "accountTypes.ts"

#: The api container mounts only `backend/`, so `just test-backend` cannot see
#: the mirror. `just ci` — and therefore GitHub CI, which gates merges — runs
#: outside Docker from the repo root and does. Skipping is honest about that;
#: failing would make a green Docker run impossible for a reason unrelated to
#: the code under test.
needs_frontend_tree = pytest.mark.skipif(
    not MIRROR.exists(), reason="frontend tree not mounted (Docker); enforced by `just ci`"
)


#: A TS string literal, in either quote style. Prettier writes a string
#: containing an apostrophe with double quotes rather than escaping it, so a
#: single-quote-only pattern silently read half of "the vehicle's value" and
#: reported the mirror as drifted. The formatter is allowed to pick; this has
#: to read whatever it picked.
_STRING = re.compile(
    r"'((?:[^'\\]|\\.)*)'"  # single-quoted
    r'|"((?:[^"\\]|\\.)*)"'  # double-quoted
)


def _strings(text: str) -> list[str]:
    return [
        (m.group(1) if m.group(1) is not None else m.group(2))
        .replace("\\'", "'")
        .replace('\\"', '"')
        for m in _STRING.finditer(text)
    ]


def _field(block: str, name: str) -> str:
    return _strings(re.search(rf"{name}:\s*(.*)", block).group(1))[0]


def _parse_mirror() -> dict[str, dict]:
    """Pull the object literals out of the TS constant.

    A parser rather than a build step: the file is hand-edited and human-read,
    and generating it would trade a drift problem for a codegen one.
    """
    source = MIRROR.read_text()
    body = source[source.index("BUILTIN_ACCOUNT_TYPES") : source.rindex("\n]")]
    entries: dict[str, dict] = {}
    for block in re.findall(r"\{(.*?)\n  \}", body, re.S):
        key = _field(block, "key")
        label = _field(block, "label")
        classification = _field(block, "classification")
        on_budget = re.search(r"default_on_budget:\s*(true|false)", block).group(1)
        # Description may be one string literal or several joined by `+`, and
        # is the last field, so it may end the block without a newline.
        raw = block[block.index("description:") :]
        description = "".join(_strings(raw))
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
