"""Which rows a feed record may claim — txn_filters' bank-identity predicates,
as the candidate query compiles them.

A pending feed record may claim only unlinked rows. A posted one may also
claim PROVISIONALLY_LINKED rows (linked to a pending record the bank may
since have re-identified), and never a legacy `cleared` row whose posted
date was simply never recorded.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import sqlite

from igab.repositories.transaction_repo import TransactionRepository


def _repo() -> TransactionRepository:
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    repo = TransactionRepository.__new__(TransactionRepository)
    repo.session = session
    return repo


def _sql(repo: TransactionRepository) -> str:
    stmt = repo.session.execute.call_args[0][0]
    return str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


async def test_pending_feed_keeps_unlinked_only():
    repo = _repo()
    await repo.find_existing_match_candidates(
        MagicMock(), Decimal("-1"), date(2026, 7, 1), include_provisional=False
    )
    sql = _sql(repo)
    assert "sync_id IS NULL" in sql
    assert "bank_posted_date IS NULL" not in sql


async def test_posted_feed_widens_candidates_to_provisionally_linked_rows():
    repo = _repo()
    await repo.find_existing_match_candidates(
        MagicMock(), Decimal("-1"), date(2026, 7, 1), include_provisional=True
    )
    sql = _sql(repo)
    assert "sync_id IS NULL" in sql
    assert "bank_posted_date IS NULL" in sql
    # The cleared guard that keeps legacy cleared rows out.
    assert "cleared IN ('pending', 'uncleared')" in sql


async def test_stale_provisional_links_are_uncleared_user_rows_only():
    repo = _repo()
    await repo.find_stale_provisional_links(MagicMock(), "simplefin", None, {"t-live"})
    sql = _sql(repo)
    assert "cleared = 'uncleared'" in sql
    assert "bank_posted_date IS NULL" in sql
    assert "NOT IN ('t-live')" in sql
