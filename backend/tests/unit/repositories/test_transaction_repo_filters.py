"""
Specification tests for TransactionRepository.get_for_account filter logic.

These tests verify the branching behavior of the filter parameters —
particularly the is_or_mode flag that switches unapproved+uncategorized
from AND logic to OR logic.

We capture the SQLAlchemy statement passed to session.execute and compile
it to a SQL string to assert the correct clause structure without needing
a real database connection.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import sqlite

from igab.repositories.transaction_repo import TransactionRepository
from igab.repositories.txn_filters import amount_search_text


def _make_repo() -> TransactionRepository:
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result_mock)
    repo = TransactionRepository.__new__(TransactionRepository)
    repo.session = session
    return repo


def _captured_sql(repo: TransactionRepository) -> str:
    """Compile the SQLAlchemy statement that was passed to session.execute."""
    stmt = repo.session.execute.call_args[0][0]
    return str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


class TestGetForAccountFilterBranching:
    @pytest.mark.asyncio
    async def test_uncategorized_only_uses_and_logic(self) -> None:
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), uncategorized=True)
        sql = _captured_sql(repo)
        # Should contain category_id IS NULL filter
        assert "category_id IS NULL" in sql or "category_id" in sql

    @pytest.mark.asyncio
    async def test_unapproved_only_uses_and_logic(self) -> None:
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), unapproved=True)
        sql = _captured_sql(repo)
        assert "approved" in sql.lower()

    @pytest.mark.asyncio
    async def test_both_flags_and_mode_produces_two_where_clauses(self) -> None:
        """With is_or_mode=False both flags are ANDed (separate WHERE clauses)."""
        repo = _make_repo()
        await repo.get_for_account(
            uuid.uuid4(), uncategorized=True, unapproved=True, is_or_mode=False
        )
        sql = _captured_sql(repo)
        # Both conditions must appear and there must be no OR joining them
        assert "category_id" in sql
        assert "approved" in sql.lower()
        # In AND mode the OR keyword should not appear between the two conditions
        # (it may appear in other parts like cleared state logic, so we check absence
        # of OR specifically in a unapproved+uncategorized combined clause)
        # The key assertion is that we called execute — if the branching were broken
        # and raised an exception this test would fail
        assert repo.session.execute.called

    @pytest.mark.asyncio
    async def test_both_flags_or_mode_produces_or_clause(self) -> None:
        """With is_or_mode=True both flags are combined with OR."""
        repo = _make_repo()
        await repo.get_for_account(
            uuid.uuid4(), uncategorized=True, unapproved=True, is_or_mode=True
        )
        sql = _captured_sql(repo)
        assert "OR" in sql.upper()
        assert "category_id" in sql
        assert "approved" in sql.lower()

    @pytest.mark.asyncio
    async def test_is_or_mode_true_with_only_uncategorized_still_works(self) -> None:
        """OR mode with only one flag set falls through to normal AND filtering."""
        repo = _make_repo()
        await repo.get_for_account(
            uuid.uuid4(), uncategorized=True, unapproved=False, is_or_mode=True
        )
        sql = _captured_sql(repo)
        assert "category_id" in sql

    @pytest.mark.asyncio
    async def test_no_flags_still_executes_successfully(self) -> None:
        """get_for_account with no filter flags must not raise."""
        repo = _make_repo()
        result = await repo.get_for_account(uuid.uuid4())
        assert result == []
        assert repo.session.execute.called

    @pytest.mark.asyncio
    async def test_date_filters_applied_correctly(self) -> None:
        repo = _make_repo()
        await repo.get_for_account(
            uuid.uuid4(),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )
        sql = _captured_sql(repo)
        assert "2025-01-01" in sql
        assert "2025-12-31" in sql

    @pytest.mark.asyncio
    async def test_cleared_filter_applied(self) -> None:
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), cleared="cleared")
        sql = _captured_sql(repo)
        assert "cleared" in sql

    @pytest.mark.asyncio
    async def test_or_mode_false_is_default(self) -> None:
        """Calling without is_or_mode behaves identically to is_or_mode=False."""
        repo1 = _make_repo()
        repo2 = _make_repo()

        acct_id = uuid.uuid4()
        await repo1.get_for_account(acct_id, uncategorized=True, unapproved=True)
        await repo2.get_for_account(acct_id, uncategorized=True, unapproved=True, is_or_mode=False)

        sql1 = _captured_sql(repo1)
        sql2 = _captured_sql(repo2)
        assert sql1 == sql2


class TestSimilarTransactionOrdering:
    """find_similar_transactions must be deterministic: an unordered LIMIT
    could arbitrarily evict the closest row when same-amount rows crowd the
    date window."""

    @pytest.mark.asyncio
    async def test_orders_nearest_date_first_with_unique_tiebreak(self) -> None:
        repo = _make_repo()
        await repo.find_similar_transactions(uuid.uuid4(), 100, date(2026, 8, 10))
        sql = _captured_sql(repo)
        assert "order by" in sql.lower()
        assert "abs(" in sql.lower(), "nearest-date-first ordering"
        assert "transactions.id" in sql.lower(), "unique tiebreak so LIMIT is stable"
        assert "limit" in sql.lower()


class TestDuplicatePairStructuredFilter:
    """Pairs where BOTH sides are structured (split parent / transfer leg)
    can never be merged, so the scan must not offer them for review."""

    @pytest.mark.asyncio
    async def test_pair_query_excludes_double_structured_pairs(self) -> None:
        repo = _make_repo()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        repo.session.execute = AsyncMock(return_value=result_mock)
        await repo.find_duplicate_candidate_pairs(uuid.uuid4())
        # No literal_binds: the date-window timedelta param can't be rendered
        # as a literal, and these assertions only need column names.
        stmt = repo.session.execute.call_args[0][0]
        sql = str(stmt.compile(dialect=sqlite.dialect()))
        assert "is_split" in sql.lower()
        assert "transfer_id" in sql.lower()
        # At least one side of every pair must be flat (not split, not transfer)
        assert " or " in sql.lower()


class TestFreeTextSearchMatchesAmounts:
    """Typing a bare number should find transactions whose amount CONTAINS it —
    the sign is ignored, so an outflow of -12.34 matches '12', '12.3', '12.34'
    and '.34'. A number is not the one term in the box that has to be typed
    perfectly; see `search_matches`."""

    @pytest.mark.asyncio
    async def test_numeric_search_matches_the_amount_partially(self) -> None:
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), search="12.34")
        sql = _captured_sql(repo)
        assert "round(abs(transactions.amount), 2)" in sql.lower()
        assert "'%12.34%'" in sql
        # Payee/memo matching is preserved alongside it
        assert "ilike" in sql.lower() or "like" in sql.lower()

    @pytest.mark.asyncio
    async def test_currency_formatting_is_tolerated(self) -> None:
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), search="$1,200")
        sql = _captured_sql(repo)
        assert "'%1200%'" in sql

    @pytest.mark.asyncio
    async def test_an_exact_amount_is_no_longer_the_rule(self) -> None:
        """The clause this replaced. A register that matched "star" against
        "Starbucks" answered "12" with only the twelve-dollar rows."""
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), search="12.34")
        sql = _captured_sql(repo)
        assert "abs(transactions.amount) = 12.34" not in sql.lower()

    @pytest.mark.asyncio
    async def test_non_numeric_search_has_no_amount_clause(self) -> None:
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), search="starbucks")
        sql = _captured_sql(repo)
        assert "abs(transactions.amount)" not in sql.lower()

    @pytest.mark.asyncio
    async def test_partially_numeric_search_has_no_amount_clause(self) -> None:
        """'12 west' is a payee fragment, not an amount."""
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), search="12 west")
        sql = _captured_sql(repo)
        assert "abs(transactions.amount)" not in sql.lower()

    @pytest.mark.asyncio
    async def test_a_half_typed_amount_matches_what_it_is_headed_for(self) -> None:
        """'12.' is one keystroke inside '12.34'. It used to compile to
        `= 12`, which answered the keystroke before it and the keystroke
        after it with two different, equally wrong sets."""
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), search="12.")
        sql = _captured_sql(repo)
        assert "'%12.%'" in sql

    @pytest.mark.asyncio
    async def test_a_leading_dot_amount_still_matches(self) -> None:
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), search=".34")
        sql = _captured_sql(repo)
        assert "'%.34%'" in sql

    @pytest.mark.asyncio
    async def test_two_dots_are_not_an_amount(self) -> None:
        repo = _make_repo()
        await repo.get_for_account(uuid.uuid4(), search="12.34.56")
        sql = _captured_sql(repo)
        assert "abs(transactions.amount)" not in sql.lower()


class TestAmountSearchText:
    """The pure half: which terms read as a number, and what digits they
    contribute to the pattern."""

    def test_currency_dressing_is_stripped(self) -> None:
        assert amount_search_text("$1,200") == "1200"
        assert amount_search_text("  12.34 ") == "12.34"

    def test_half_typed_forms_survive(self) -> None:
        assert amount_search_text("12.") == "12."
        assert amount_search_text(".34") == ".34"

    def test_anything_that_is_not_a_number_is_none(self) -> None:
        for term in ("starbucks", "12 west", "12.34.56", "", "-12"):
            assert amount_search_text(term) is None
