"""The feature registry is the only place a call may be named.

A call logged under a name nobody declared is a call nobody can explain later,
so this scans the source rather than trusting a convention. The same technique
`queryKeys.deadRoots.test.ts` uses on the frontend.
"""

import re
from pathlib import Path

import pytest

from igab.ai.features import FEATURES, UnknownFeature, describe

SRC = Path(__file__).resolve().parents[2] / "src" / "igab"

#: `feature="..."` as written at a call site.
_FEATURE_LITERAL = re.compile(r'feature=["\']([a-z_]+)["\']')


def _declared_features_in_source() -> set[str]:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        if path.name == "features.py":
            continue
        found.update(_FEATURE_LITERAL.findall(path.read_text()))
    return found


class TestEveryFeatureIsDeclared:
    def test_no_call_site_invents_a_feature(self):
        """Adding a `feature=` literal without a registry row fails here,
        rather than shipping an activity-log row that says nothing."""
        undeclared = _declared_features_in_source() - set(FEATURES)
        assert not undeclared, (
            f"{sorted(undeclared)} appear as feature= at a call site but are not "
            f"in igab.ai.features.FEATURES. Add a row saying what the call is for."
        )

    def test_the_source_actually_uses_features(self):
        """Guards the guard: a regex that matches nothing would pass forever."""
        assert len(_declared_features_in_source()) >= 5

    def test_every_description_reads_as_a_sentence(self):
        for feature, description in FEATURES.items():
            assert description.endswith("."), feature
            assert description[0].isupper(), feature


class TestDescribe:
    def test_known_feature(self):
        assert describe("chat").startswith("Answering")

    def test_unknown_feature_raises(self):
        """Raising rather than defaulting: a label nobody declared is a bug."""
        with pytest.raises(UnknownFeature):
            describe("not_a_feature")
