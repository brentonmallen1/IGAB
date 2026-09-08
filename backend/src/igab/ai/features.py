"""Every AI feature this app has, named once.

A *feature* is one reason the app talks to a model. It is the label on a call
in the activity log, the key a per-feature setting would hang off, and the
thing a user reads when asking "what did the AI do and why".

The registry is a plain frozen mapping rather than a table, because that is
what this repo already does for a fixed vocabulary — see `guide/concepts.py`.
`tests/unit/test_ai_features.py` scans the source for `feature=` literals and
fails on one that is not declared here, so the mapping cannot go stale while a
new call site quietly invents its own name.

Descriptions are user-facing: they appear next to the call in AI Activity.
"""

from collections.abc import Mapping
from types import MappingProxyType

#: feature id -> what it is, in the user's terms.
FEATURES: Mapping[str, str] = MappingProxyType(
    {
        "receipt_gate": "Deciding whether a photo is a receipt at all.",
        "receipt_extract": "Reading a receipt photo into a transaction.",
        "nl_parse": "Turning a typed description into a transaction.",
        "suggest_category": "Suggesting which envelope a transaction belongs in.",
        "suggest_regex": "Suggesting a match pattern for a set of payee names.",
        "spending_insights": "Summarising a month's spending.",
        "chat": "Answering a question you asked in the chat panel.",
        "chat_title": "Naming a conversation from its first message.",
    }
)


class UnknownFeature(KeyError):
    """A call named a feature the registry does not declare."""


def describe(feature: str) -> str:
    """The user-facing description, or raise — an unnamed feature is a bug.

    Raising rather than defaulting is the point: a call logged under a name
    nobody declared is a call nobody can explain later.
    """
    try:
        return FEATURES[feature]
    except KeyError:
        raise UnknownFeature(feature) from None
