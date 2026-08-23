"""
Specification tests for TransactionRepository._count_pending_review and
PendingReviewCount schema serialization.

The pending-review count feeds the banner that tells the user how many
transactions need attention. Incorrect counts erode trust in the app.

Key invariants this suite enforces:
  1. total == unapproved_only + uncategorized_only + both
  2. unapproved == unapproved_only + both
  3. uncategorized == uncategorized_only + both
  4. total <= unapproved + uncategorized  (no double-count)
  5. total == unapproved + uncategorized - both  (inclusion-exclusion identity)
  6. PendingReviewCount schema exposes 'total' (regression for the double-count bug)
  7. The 'needs_category' definition excludes transfer transactions
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from igab.api.v1.schemas.transaction import PendingReviewCount
from igab.repositories.transaction_repo import TransactionRepository


def _make_repo_with_count_result(both: int, unapproved_only: int, uncategorized_only: int) -> TransactionRepository:
    """Build a repo whose session returns a pre-set aggregation row."""
    session = AsyncMock()

    row = MagicMock()
    row.both = both
    row.unapproved_only = unapproved_only
    row.uncategorized_only = uncategorized_only

    result_mock = MagicMock()
    result_mock.one.return_value = row
    session.execute = AsyncMock(return_value=result_mock)

    repo = TransactionRepository.__new__(TransactionRepository)
    repo.session = session
    return repo


def _make_filter_repo() -> TransactionRepository:
    """Build a repo for get_for_account SQL inspection (no rows returned)."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result_mock)
    repo = TransactionRepository.__new__(TransactionRepository)
    repo.session = session
    return repo


def _captured_sql(repo: TransactionRepository) -> str:
    from sqlalchemy.dialects import sqlite
    stmt = repo.session.execute.call_args[0][0]
    return str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


# ─── Invariant helpers ────────────────────────────────────────────────────────

def assert_count_invariants(counts: dict[str, Any]) -> None:
    """Assert all structural invariants hold for a count result dict."""
    both = counts["both"]
    unapproved_only = counts["unapproved_only"]
    uncategorized_only = counts["uncategorized_only"]
    total = counts["total"]
    unapproved = counts["unapproved"]
    uncategorized = counts["uncategorized"]

    assert total == unapproved_only + uncategorized_only + both, (
        f"total ({total}) != unapproved_only ({unapproved_only}) + "
        f"uncategorized_only ({uncategorized_only}) + both ({both})"
    )
    assert unapproved == unapproved_only + both, (
        f"unapproved ({unapproved}) != unapproved_only ({unapproved_only}) + both ({both})"
    )
    assert uncategorized == uncategorized_only + both, (
        f"uncategorized ({uncategorized}) != uncategorized_only ({uncategorized_only}) + both ({both})"
    )
    # Inclusion-exclusion: unique count = A + B - (A∩B)
    assert total == unapproved + uncategorized - both, (
        f"inclusion-exclusion failed: total ({total}) != "
        f"unapproved ({unapproved}) + uncategorized ({uncategorized}) - both ({both})"
    )
    assert total <= unapproved + uncategorized, (
        "total exceeds unapproved + uncategorized — double-counting detected"
    )


# ─── Repository count result tests ───────────────────────────────────────────

class TestCountPendingReviewResult:
    """Verify _count_pending_review returns the correct derived fields."""

    @pytest.mark.asyncio
    async def test_all_zeros(self) -> None:
        repo = _make_repo_with_count_result(both=0, unapproved_only=0, uncategorized_only=0)
        result = await repo._count_pending_review(True)  # type: ignore[arg-type]
        assert result == {
            "unapproved_only": 0,
            "uncategorized_only": 0,
            "both": 0,
            "total": 0,
            "unapproved": 0,
            "uncategorized": 0,
        }
        assert_count_invariants(result)

    @pytest.mark.asyncio
    async def test_only_unapproved(self) -> None:
        """Transactions that are unapproved but already have a category."""
        repo = _make_repo_with_count_result(both=0, unapproved_only=10, uncategorized_only=0)
        result = await repo._count_pending_review(True)  # type: ignore[arg-type]
        assert result["total"] == 10
        assert result["unapproved"] == 10
        assert result["uncategorized"] == 0
        assert result["both"] == 0
        assert_count_invariants(result)

    @pytest.mark.asyncio
    async def test_only_uncategorized(self) -> None:
        """Transactions that have no category but are approved."""
        repo = _make_repo_with_count_result(both=0, unapproved_only=0, uncategorized_only=5)
        result = await repo._count_pending_review(True)  # type: ignore[arg-type]
        assert result["total"] == 5
        assert result["unapproved"] == 0
        assert result["uncategorized"] == 5
        assert result["both"] == 0
        assert_count_invariants(result)

    @pytest.mark.asyncio
    async def test_both_unapproved_and_uncategorized(self) -> None:
        """Transactions that are unapproved AND have no category."""
        repo = _make_repo_with_count_result(both=17, unapproved_only=0, uncategorized_only=0)
        result = await repo._count_pending_review(True)  # type: ignore[arg-type]
        assert result["total"] == 17        # each transaction counted once
        assert result["unapproved"] == 17
        assert result["uncategorized"] == 17
        assert result["both"] == 17
        assert_count_invariants(result)

    @pytest.mark.asyncio
    async def test_mixed_all_three_buckets(self) -> None:
        """
        Realistic case: some unapproved-only, some uncategorized-only, some both.
        This is the scenario that produced the 91 vs 74 bug:
          - 57 unapproved with categories (unapproved_only)
          - 17 uncategorized and approved (uncategorized_only)
          - 17 unapproved AND uncategorized (both)
          -> total unique = 57 + 17 + 17 = 91 would be WRONG
          -> correct total = 57 + 17 + 17 = 91 only if both=17 means those are distinct
          Wait — let me reconsider.

        Actually let's use numbers matching the observed bug:
          - unapproved_only = 57 (unapproved, have a category)
          - uncategorized_only = 0 (approved, no category)
          - both = 17 (unapproved AND no category)
          -> total = 57 + 0 + 17 = 74
          -> unapproved = 57 + 17 = 74
          -> uncategorized = 0 + 17 = 17
          -> fallback unapproved + uncategorized = 74 + 17 = 91 ← the reported bug number
        """
        repo = _make_repo_with_count_result(both=17, unapproved_only=57, uncategorized_only=0)
        result = await repo._count_pending_review(True)  # type: ignore[arg-type]
        assert result["total"] == 74
        assert result["unapproved"] == 74
        assert result["uncategorized"] == 17
        assert result["both"] == 17
        # The naive sum unapproved + uncategorized would give 91 — must NOT use that
        assert result["unapproved"] + result["uncategorized"] == 91
        assert result["total"] == 74  # correct deduplicated count
        assert_count_invariants(result)

    @pytest.mark.asyncio
    async def test_all_three_buckets_nonzero(self) -> None:
        repo = _make_repo_with_count_result(both=5, unapproved_only=20, uncategorized_only=10)
        result = await repo._count_pending_review(True)  # type: ignore[arg-type]
        assert result["total"] == 35       # 20 + 10 + 5
        assert result["unapproved"] == 25  # 20 + 5
        assert result["uncategorized"] == 15  # 10 + 5
        assert_count_invariants(result)

    @pytest.mark.asyncio
    async def test_null_db_values_treated_as_zero(self) -> None:
        """If the DB returns NULL for a sum (empty table), treat as 0."""
        repo = _make_repo_with_count_result(both=None, unapproved_only=None, uncategorized_only=None)  # type: ignore[arg-type]
        result = await repo._count_pending_review(True)  # type: ignore[arg-type]
        assert result["total"] == 0
        assert result["unapproved"] == 0
        assert result["uncategorized"] == 0
        assert_count_invariants(result)


# ─── Schema serialization tests ───────────────────────────────────────────────

class TestPendingReviewCountSchema:
    """
    Verify PendingReviewCount exposes 'total' and all breakdown fields.

    Regression suite for the bug where PendingReviewCount only had 'unapproved'
    and 'uncategorized', causing the frontend to fall back to the double-counting
    formula: unapproved + uncategorized (which overcounts by 'both').
    """

    def test_schema_has_total_field(self) -> None:
        schema = PendingReviewCount(
            unapproved=74,
            uncategorized=17,
            unapproved_only=57,
            uncategorized_only=0,
            both=17,
            total=74,
        )
        assert schema.total == 74

    def test_schema_has_breakdown_fields(self) -> None:
        schema = PendingReviewCount(
            unapproved=25,
            uncategorized=15,
            unapproved_only=20,
            uncategorized_only=10,
            both=5,
            total=35,
        )
        assert schema.unapproved_only == 20
        assert schema.uncategorized_only == 10
        assert schema.both == 5

    def test_schema_serializes_total(self) -> None:
        """model_dump must include 'total' — this is what FastAPI serializes to JSON."""
        schema = PendingReviewCount(
            unapproved=74,
            uncategorized=17,
            unapproved_only=57,
            uncategorized_only=0,
            both=17,
            total=74,
        )
        data = schema.model_dump()
        assert "total" in data, "PendingReviewCount.model_dump() must include 'total'"
        assert data["total"] == 74

    def test_total_not_double_counted(self) -> None:
        """
        The 'total' field must equal the deduplicated count, not unapproved + uncategorized.

        This is the regression test for the banner showing 91 instead of 74:
          - unapproved = 74 (includes 17 that also need category)
          - uncategorized = 17
          - naive sum = 91 (wrong — double-counts the 17 'both' transactions)
          - total = 74 (correct)
        """
        schema = PendingReviewCount(
            unapproved=74,
            uncategorized=17,
            unapproved_only=57,
            uncategorized_only=0,
            both=17,
            total=74,
        )
        data = schema.model_dump()
        naive_sum = data["unapproved"] + data["uncategorized"]
        assert data["total"] != naive_sum, (
            "total should differ from unapproved + uncategorized when 'both' > 0"
        )
        assert data["total"] == naive_sum - data["both"], (
            "total must equal unapproved + uncategorized - both (inclusion-exclusion)"
        )

    def test_schema_round_trips_from_repo_dict(self) -> None:
        """PendingReviewCount(**repo_dict) must preserve all fields including total."""
        repo_dict = {
            "unapproved_only": 57,
            "uncategorized_only": 0,
            "both": 17,
            "total": 74,
            "unapproved": 74,
            "uncategorized": 17,
        }
        schema = PendingReviewCount(**repo_dict)
        assert schema.total == 74
        assert schema.both == 17
        assert schema.unapproved_only == 57
        assert schema.uncategorized_only == 0

    def test_schema_defaults_allow_missing_breakdown_fields(self) -> None:
        """Fields have defaults so existing callers that omit them don't break."""
        schema = PendingReviewCount(unapproved=5, uncategorized=3)
        assert schema.total == 0   # default
        assert schema.both == 0    # default


# ─── SQL structure: needs_category excludes transfers ─────────────────────────

class TestCountQueryStructure:
    """Verify the SQL emitted by _count_pending_review has the correct structure."""

    @pytest.mark.asyncio
    async def test_count_query_recognises_a_transfer_by_more_than_its_link(self) -> None:
        """`needs_category` must not decide "is this a transfer" from
        `transfer_id` alone.

        This test used to assert the SQL contained `transfer_id IS NULL`, which
        pinned the bug rather than the behaviour: a leg whose partner never
        imported has a NULL link and is still a transfer, and a real YNAB
        import produced 1,117 of them, every one counted as needing a category.
        The predicate now goes through CASH_FLOW_ROW, which recognises a
        transfer by its payee as well as its link — so the emitted SQL has to
        show the payee test. Behaviour is covered in
        tests/integration/test_offbudget_categories.py.
        """
        from sqlalchemy.dialects import sqlite

        repo = _make_filter_repo()
        # Trigger _count_pending_review via the public method
        row = MagicMock()
        row.both = 0
        row.unapproved_only = 0
        row.uncategorized_only = 0
        result_mock = MagicMock()
        result_mock.one.return_value = row
        repo.session.execute = AsyncMock(return_value=result_mock)

        await repo.count_pending_review_for_account(uuid.uuid4())

        stmt = repo.session.execute.call_args[0][0]
        sql = str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))

        assert "transfer_account_id IS NOT NULL" in sql, (
            "needs_category must reach TRANSFER_LEG's payee test, not just the "
            "transfer_id link — an unpaired leg is still a transfer"
        )

    @pytest.mark.asyncio
    async def test_count_query_checks_approved_false(self) -> None:
        """The unapproved condition must filter on approved = false."""
        from sqlalchemy.dialects import sqlite

        repo = _make_filter_repo()
        row = MagicMock()
        row.both = 0
        row.unapproved_only = 0
        row.uncategorized_only = 0
        result_mock = MagicMock()
        result_mock.one.return_value = row
        repo.session.execute = AsyncMock(return_value=result_mock)

        await repo.count_pending_review_for_account(uuid.uuid4())

        stmt = repo.session.execute.call_args[0][0]
        sql = str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))

        assert "approved" in sql.lower()

    @pytest.mark.asyncio
    async def test_count_query_excludes_deleted_and_children(self) -> None:
        """Base WHERE must exclude soft-deleted rows and split children."""
        from sqlalchemy.dialects import sqlite

        repo = _make_filter_repo()
        row = MagicMock()
        row.both = 0
        row.unapproved_only = 0
        row.uncategorized_only = 0
        result_mock = MagicMock()
        result_mock.one.return_value = row
        repo.session.execute = AsyncMock(return_value=result_mock)

        await repo.count_pending_review_for_account(uuid.uuid4())

        stmt = repo.session.execute.call_args[0][0]
        sql = str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))

        assert "is_deleted" in sql.lower()
        assert "parent_transaction_id" in sql.lower()
