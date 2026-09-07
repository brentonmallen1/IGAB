"""The tag predicate over transaction rows — `txn_filters.category_tagged` — as
it compiles. One SQL spelling: the activity classifier reads it for
savings/debt, the Subscriptions report and the cash projection read it for
subscriptions, and `ESSENTIAL_TAGGED` is it.
"""

from sqlalchemy.dialects import sqlite

from igab.repositories.txn_filters import ESSENTIAL_TAGGED, category_tagged


def _sql(expr) -> str:
    return str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


def test_category_tagged_keeps_the_null_guard():
    sql = _sql(category_tagged("essential"))
    assert "category_id IS NOT NULL" in sql, "NULL IN (...) is UNKNOWN, never FALSE"
    assert "system_key IN ('essential')" in sql
    assert "category_tags" in sql and "payee_tags" not in sql


def test_essential_reads_categories_and_nothing_else():
    """`ESSENTIAL_TAGGED` was `or_(category_tagged, payee_tagged)`, and the
    payee arm was the last rule in the app that read a tag on a payee for
    meaning. Tags on payees are retired; this is what makes that true rather
    than merely intended, since a leftover OR would still count them."""
    sql = _sql(ESSENTIAL_TAGGED)
    assert "category_tags" in sql
    assert "payee_tags" not in sql
    assert " OR " not in sql
