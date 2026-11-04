"""`ON_BUDGET_ACCOUNT` and `ON_CARD_ACCOUNT` are planned once, not per row.

Both used to correlate their subquery to the outer row
(`Account.budget_id == Transaction.budget_id`), which Postgres can only run as
a subplan per transaction scanned: 28 of the 46 ms of the Budget page's
activity sum, 70 of the 77 ms of the card walk's unclaimed-row sum, on ten
years of history. They now carry the budget in the row value instead —
`(account_id, budget_id) IN (SELECT id, budget_id ...)` — which names nothing
outside itself and is hashed once. The rows matched are the same; whether
they are is the integration suite's job (`class_agreement`, the card
scenarios). These pin the *shape*, so a later edit cannot quietly put the
correlation back.
"""

import re

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from igab.db.models import Account, Transaction
from igab.repositories.txn_filters import ON_BUDGET_ACCOUNT, ON_CARD_ACCOUNT

PREDICATES = {"ON_BUDGET_ACCOUNT": ON_BUDGET_ACCOUNT, "ON_CARD_ACCOUNT": ON_CARD_ACCOUNT}


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def _subquery(sql: str) -> str:
    """The text of the IN (...) subquery."""
    match = re.search(r"IN \((SELECT .*?)\)(?:\s|$)", sql, re.S)
    assert match, sql
    return match.group(1)


@pytest.mark.parametrize("name", PREDICATES)
def test_the_subquery_names_nothing_outside_itself(name):
    sql = _sql(select(Transaction.id).where(PREDICATES[name]))
    assert "(transactions.account_id, transactions.budget_id) IN" in sql
    assert "transactions." not in _subquery(sql)


@pytest.mark.parametrize("name", PREDICATES)
def test_a_query_that_joins_accounts_does_not_capture_the_subquery(name):
    """Correlated to the outer join's `accounts`, the subquery would lose
    its FROM and test the joined account alone — the per-row plan again, and
    a different question. It keeps its own (`correlate(None)`)."""
    stmt = (
        select(Transaction.id)
        .join(Account, Account.id == Transaction.account_id)
        .where(PREDICATES[name])
    )
    assert "FROM accounts" in _subquery(_sql(stmt))
