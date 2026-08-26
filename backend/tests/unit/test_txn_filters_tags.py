"""The tag predicates over transaction rows — txn_filters.category_tagged and
payee_tagged — as they compile. One SQL spelling: the activity classifier
reads the first for savings/debt, the essentials report reads both."""

from sqlalchemy.dialects import sqlite

from igab.repositories.txn_filters import ESSENTIAL_TAGGED, category_tagged, payee_tagged


def _sql(expr) -> str:
    return str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


def test_category_tagged_keeps_the_null_guard():
    sql = _sql(category_tagged("essential"))
    assert "category_id IS NOT NULL" in sql, "NULL IN (...) is UNKNOWN, never FALSE"
    assert "system_key IN ('essential')" in sql
    assert "category_tags" in sql and "payee_tags" not in sql


def test_payee_tagged_mirrors_it():
    sql = _sql(payee_tagged("essential"))
    assert "payee_id IS NOT NULL" in sql
    assert "payee_tags" in sql and "category_tags" not in sql


def test_essential_is_category_or_payee():
    sql = _sql(ESSENTIAL_TAGGED)
    assert "category_tags" in sql and "payee_tags" in sql
    assert " OR " in sql
