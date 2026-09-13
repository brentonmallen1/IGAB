"""The rule ladder, given literal booleans instead of columns.

`literal_inputs` lets the Guide ask the shipped rules about a row that does
not exist. That only works if the rules read nothing except `_Inputs` — so
moving the row facts into `_Inputs` had to leave the SQL the reports run
byte-for-byte unchanged, and a rule that reads a column directly again must
fail here rather than silently answer the Guide with a bound column.
"""

import os
from dataclasses import fields
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import BindParameter
from sqlalchemy.sql.schema import Column

import igab.domain.activity_class as ac

SNAPSHOT = Path(__file__).parent / "snapshots" / "activity_class_rules.sql"


def _compiled() -> str:
    dialect = postgresql.dialect()
    parts = []
    for name in (
        "ACTIVITY_CLASS",
        "ACTIVITY_REASON",
        "ACTIVITY_CLASS_SUBQUERY",
        "ACTIVITY_REASON_SUBQUERY",
    ):
        expr = getattr(ac, name)
        parts.append(f"-- {name}")
        parts.append(str(expr.compile(dialect=dialect, compile_kwargs={"literal_binds": True})))
    return "\n".join(parts) + "\n"


def test_the_compiled_classifier_is_unchanged():
    """Captured before the row facts moved into `_Inputs`.

    A deliberate rule change regenerates it:
    `IGAB_REGEN_RULE_SQL=1 uv run pytest tests/unit/test_literal_rules.py`
    — and the diff of this file is then the review of what the reports now run.
    """
    if os.environ.get("IGAB_REGEN_RULE_SQL"):
        SNAPSHOT.write_text(_compiled())
    assert _compiled() == SNAPSHOT.read_text()


def test_leg_facts_name_every_input_and_nothing_else():
    assert {f.name for f in fields(ac.LegFacts)} == {f.name for f in fields(ac._Inputs)}


def test_the_literal_rules_read_no_column():
    """Every leaf of the literal ladder is a bound value. A column here means a
    rule reads a table directly, and the Guide's answer would come from a
    FROM-less SELECT that cannot see one."""
    facts = ac.LegFacts(**dict.fromkeys(ac.LegFacts.__dataclass_fields__, False))
    for condition, _, _ in ac._rules(ac.literal_inputs(facts)):
        leaves = list(visitors.iterate(condition))
        assert not [n for n in leaves if isinstance(n, Column)]
        assert [n for n in leaves if isinstance(n, BindParameter)]


def test_tag_inputs_read_the_tags_they_are_named_for():
    """`_ROW_FACTS` builds each tag predicate from `TAG_INPUT_KEYS`; this pins
    that the compiled predicate names the key it is paired with."""
    dialect = postgresql.dialect()
    for field, key in ac.TAG_INPUT_KEYS.items():
        sql = str(
            ac._ROW_FACTS[field].compile(dialect=dialect, compile_kwargs={"literal_binds": True})
        )
        assert f"('{key}')" in sql


def test_the_ladder_follows_the_shipped_rules_in_order():
    ladder = ac.rule_ladder()
    assert [r.reason for r in ladder] == list(ac.REASON_PRIORITY)
    assert [r.cls for r in ladder[:-1]] == [cls for _, cls, _ in ac.RULES]
    assert ladder[-1].cls is ac.ActivityClass.SPENDING


def test_the_ladder_finds_the_tag_rules_by_reading_them():
    tagged = {r.reason: r.tag_key for r in ac.rule_ladder() if r.tag_key}
    assert tagged == {
        ac.ActivityReason.TAGGED_SAVINGS: "savings",
        ac.ActivityReason.TAGGED_DEBT: "debt_principal",
    }


def test_a_tag_without_a_category_is_refused():
    base = dict.fromkeys(ac.LegFacts.__dataclass_fields__, False)
    for field in ("tagged_savings", "tagged_debt", "in_system_group"):
        try:
            ac.LegFacts(**{**base, field: True})
        except ValueError:
            continue
        raise AssertionError(f"{field} without categorized was accepted")
