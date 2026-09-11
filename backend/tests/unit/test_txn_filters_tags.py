"""The tag predicate over transaction rows — `txn_filters.category_tagged` — as
it compiles. One SQL spelling: the activity classifier reads it for
savings/debt, the Subscriptions report and the cash projection read it for
subscriptions, and each necessity tier's tag arm is it, over the keys in
`TIER_TAG_KEYS`.
"""

import re

import pytest
from sqlalchemy.dialects import sqlite

from igab.domain.activity_class import TIER_TAG_KEYS, NecessityTier, tier_scope
from igab.repositories.tag_repo import SYSTEM_TAGS
from igab.repositories.txn_filters import category_tagged


def _sql(expr) -> str:
    return str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


def test_category_tagged_keeps_the_null_guard():
    sql = _sql(category_tagged("essential"))
    assert "category_id IS NOT NULL" in sql, "NULL IN (...) is UNKNOWN, never FALSE"
    assert "system_key IN ('essential')" in sql
    assert "category_tags" in sql and "payee_tags" not in sql


def test_essential_reads_categories_and_nothing_else():
    """The Essential arm was `or_(category_tagged, payee_tagged)`, and the
    payee arm was the last rule in the app that read a tag on a payee for
    meaning. Tags on payees are retired; this is what makes that true rather
    than merely intended, since a leftover OR would still count them."""
    sql = _sql(tier_scope(NecessityTier.ESSENTIAL))
    assert "category_tags" in sql
    assert "payee_tags" not in sql
    assert " OR " not in sql


class TestOneTierToTagMapping:
    """`tier_keys` returned literal key lists while `tier_scope` built its
    predicate from two constants that spelled the same keys again, kept in
    step by a docstring. A key added on one side would have had the
    applied-count and the WHERE clause asking about different tags — the
    payee-count bug #183 fixed, in another form. Both now read
    `TIER_TAG_KEYS`; these pin that the predicate asks about exactly those
    keys."""

    @pytest.mark.parametrize("tier", list(NecessityTier))
    def test_the_predicate_reads_exactly_the_tiers_keys(self, tier):
        # The wide tier's class arm carries the classifier's own tag tests
        # (savings, debt principal); only the lists naming a necessity key
        # are the tier's membership.
        necessity = {"essential", "cost_of_living"}
        asked = [
            {k.strip(" '") for k in listed.split(",")}
            for listed in re.findall(r"system_key IN \(([^)]*)\)", _sql(tier_scope(tier)))
        ]
        assert [keys for keys in asked if keys & necessity] == [set(TIER_TAG_KEYS[tier])]

    def test_the_wide_tier_contains_the_lean_one(self):
        lean = TIER_TAG_KEYS[NecessityTier.ESSENTIAL]
        wide = TIER_TAG_KEYS[NecessityTier.COST_OF_LIVING]
        assert set(lean) < set(wide)

    def test_every_key_is_a_seeded_system_tag(self):
        seeded = {key for key, _name, _color in SYSTEM_TAGS}
        for keys in TIER_TAG_KEYS.values():
            assert set(keys) <= seeded
