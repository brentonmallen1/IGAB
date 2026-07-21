"""
Unit tests for TransactionMatchingService accept/reject flows.

Match acceptance rules (full DB behavior verified in
tests/integration/test_simplefin_sync.py — these unit tests cover the
mock-testable guards and control flow):
  1. The pair merges down to one live row: the keeper inherits the loser's
     bank identity (sync_id/sync_source, import metadata) and the loser is
     soft-deleted FIRST (unique-index-safe ordering).
  2. A reconciled row always wins the keeper role; two reconciled rows raise.
  3. A match whose sides are missing or already deleted is auto-rejected.
  4. Re-accepting an accepted match is a no-op; a self-match is a no-op.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.services.transaction_matching_service import TransactionMatchingService

BUDGET_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def make_txn(
    *,
    sync_id: str | None = None,
    sync_source: str | None = None,
    import_id: str | None = None,
    import_description: str | None = None,
    cleared: str = "uncleared",
    has_sync_source: bool = False,
    is_deleted: bool = False,
) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.sync_id = sync_id
    t.sync_source = sync_source
    t.import_id = import_id
    t.import_description = import_description
    t.cleared = cleared
    t.has_sync_source = has_sync_source
    t.is_deleted = is_deleted
    t.payee_id = None
    t.budget_id = BUDGET_ID
    t.date = None
    t.entered_date = None
    return t


def make_match(
    *,
    synced_id: uuid.UUID | None = None,
    manual_id: uuid.UUID | None = None,
    status: str = "pending",
    confidence: float = 0.85,
) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.synced_transaction_id = synced_id or uuid.uuid4()
    m.manual_transaction_id = manual_id or uuid.uuid4()
    m.status = status
    m.confidence_score = Decimal(str(confidence))
    return m


def make_service() -> TransactionMatchingService:
    return TransactionMatchingService(
        session=AsyncMock(),
        txn_repo=AsyncMock(),
        match_repo=AsyncMock(),
        payee_repo=AsyncMock(),
    )


class TestAcceptLinkGuards:
    async def test_self_match_is_noop(self) -> None:
        svc = make_service()
        txn = make_txn(sync_id="t-1")

        await svc._accept_link(txn, txn, 0.99)

        svc.session.execute.assert_not_awaited()

    async def test_stale_deleted_side_is_noop(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-1", is_deleted=True)
        manual = make_txn()

        await svc._accept_link(synced, manual, 0.9)

        svc.session.execute.assert_not_awaited()

    async def test_both_reconciled_raises(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-1", cleared="reconciled")
        manual = make_txn(cleared="reconciled")

        with pytest.raises(InvariantViolation):
            await svc._accept_link(synced, manual, 0.9)

    async def test_conflicting_bank_identities_raise(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-1")
        manual = make_txn(sync_id="t-2")

        with pytest.raises(InvariantViolation):
            await svc._accept_link(synced, manual, 0.9)

    async def test_merge_deletes_loser_then_updates_keeper(self) -> None:
        """Ordering matters: under the partial unique index the loser's
        sync_id must leave the live set before it lands on the keeper."""
        svc = make_service()
        synced = make_txn(sync_id="t-1", sync_source="simplefin")
        manual = make_txn()

        await svc._accept_link(synced, manual, 0.9)

        calls = svc.session.execute.call_args_list
        assert len(calls) == 2
        first_sql = str(calls[0].args[0]).lower()
        second_sql = str(calls[1].args[0]).lower()
        assert "is_deleted" in first_sql, "loser must be soft-deleted first"
        assert "sync_id" in second_sql, "keeper receives the bank identity second"
        svc.session.flush.assert_awaited_once()


class TestAcceptMatch:
    async def test_accept_marks_accepted_after_successful_link(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-9", sync_source="simplefin")
        manual = make_txn()
        match = make_match(synced_id=synced.id, manual_id=manual.id)

        svc.match_repo.get = AsyncMock(return_value=match)
        svc.match_repo.update_status = AsyncMock()

        synced_result = MagicMock()
        synced_result.scalar_one_or_none = MagicMock(return_value=synced)
        manual_result = MagicMock()
        manual_result.scalar_one_or_none = MagicMock(return_value=manual)
        svc.session.execute = AsyncMock(
            side_effect=[synced_result, manual_result, None, None]
        )

        await svc.accept_match(match.id)

        svc.match_repo.update_status.assert_awaited_once_with(match.id, "accepted")

    async def test_accept_with_deleted_side_auto_rejects(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-9", is_deleted=True)
        manual = make_txn()
        match = make_match(synced_id=synced.id, manual_id=manual.id)

        svc.match_repo.get = AsyncMock(return_value=match)
        svc.match_repo.update_status = AsyncMock()

        synced_result = MagicMock()
        synced_result.scalar_one_or_none = MagicMock(return_value=synced)
        manual_result = MagicMock()
        manual_result.scalar_one_or_none = MagicMock(return_value=manual)
        svc.session.execute = AsyncMock(side_effect=[synced_result, manual_result])

        await svc.accept_match(match.id)

        svc.match_repo.update_status.assert_awaited_once_with(match.id, "rejected")

    async def test_accept_already_accepted_match_is_noop(self) -> None:
        svc = make_service()
        match = make_match(status="accepted")
        svc.match_repo.get = AsyncMock(return_value=match)
        svc.match_repo.update_status = AsyncMock()

        await svc.accept_match(match.id)

        svc.match_repo.update_status.assert_not_awaited()
        svc.session.execute.assert_not_awaited()

    async def test_accept_nonexistent_match_is_noop(self) -> None:
        svc = make_service()
        svc.match_repo.get = AsyncMock(return_value=None)
        svc.match_repo.update_status = AsyncMock()

        await svc.accept_match(uuid.uuid4())

        svc.match_repo.update_status.assert_not_awaited()


class TestRejectMatch:
    async def test_reject_match_updates_status(self) -> None:
        svc = make_service()
        match = make_match()
        svc.match_repo.update_status = AsyncMock()

        await svc.reject_match(match.id)

        svc.match_repo.update_status.assert_awaited_once_with(match.id, "rejected")

    async def test_reject_match_does_not_mutate_transactions(self) -> None:
        svc = make_service()
        match = make_match()
        svc.match_repo.update_status = AsyncMock()

        await svc.reject_match(match.id)

        svc.session.execute.assert_not_awaited()
