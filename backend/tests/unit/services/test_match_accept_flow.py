"""
Unit tests for TransactionMatchingService accept/reject flows.

Accepting a match IS a merge — TransactionService.merge, the one merge; who
survives and what the bank row contributes are decided there and pinned in
tests/integration/test_merge.py and test_match_guards.py. What is left to
this service, and covered here:
  1. A self-match or a match with a deleted side never reaches the merge.
  2. accept_match resolves the match only after a successful merge; a
     refused merge propagates and leaves the match pending.
  3. try_match writes its match row AFTER the outcome — accepted only when
     the merge happened, pending when it was refused or the score fell short.
  4. Re-accepting an accepted match is a no-op; a missing match is a no-op.
"""

import datetime
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
    is_split: bool = False,
    transfer_id: uuid.UUID | None = None,
    parent_transaction_id: uuid.UUID | None = None,
    bank_posted_date: datetime.date | None = None,
    bank_amount: Decimal | None = None,
    bank_payee: str | None = None,
    amount: str = "-25.00",
    txn_date: datetime.date | None = None,
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
    # Explicit structural defaults: MagicMock auto-attributes are truthy and
    # would otherwise trip the split/transfer guards in every test.
    t.is_split = is_split
    t.transfer_id = transfer_id
    t.parent_transaction_id = parent_transaction_id
    t.bank_posted_date = bank_posted_date
    t.bank_amount = bank_amount
    t.bank_payee = bank_payee
    t.amount = Decimal(amount)
    t.payee_id = None
    t.budget_id = BUDGET_ID
    t.date = txn_date
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
        txn_service=AsyncMock(),
    )


class TestAcceptLinkGuards:
    async def test_self_match_is_noop(self) -> None:
        svc = make_service()
        txn = make_txn(sync_id="t-1")

        await svc._accept_link(txn, txn, 0.99)

        svc.txn_service.merge.assert_not_awaited()

    async def test_stale_deleted_side_is_noop(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-1", is_deleted=True)
        manual = make_txn()

        await svc._accept_link(synced, manual, 0.99)

        svc.txn_service.merge.assert_not_awaited()

    async def test_accept_link_is_the_one_merge(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-1", sync_source="simplefin")
        manual = make_txn()

        await svc._accept_link(synced, manual, 0.99)

        svc.txn_service.merge.assert_awaited_once_with(BUDGET_ID, [synced.id, manual.id])


class TestTryMatchWritesTheRowAfterTheOutcome:
    def _svc_with_candidate(self, synced, candidate, score_patch):
        svc = make_service()
        svc.txn_repo.find_match_candidates = AsyncMock(return_value=[candidate])
        svc.payee_repo.get = AsyncMock(return_value=None)
        return svc

    async def test_accepted_only_after_the_merge_happened(self, monkeypatch) -> None:
        svc = make_service()
        synced, manual = make_txn(sync_id="t-1", sync_source="simplefin"), make_txn()
        svc.txn_repo.find_match_candidates = AsyncMock(return_value=[manual])
        svc.payee_repo.get = AsyncMock(return_value=None)
        monkeypatch.setattr(
            "igab.services.transaction_matching_service.calculate_confidence", lambda *a: 0.95
        )

        await svc.try_match(synced)

        svc.txn_service.merge.assert_awaited_once()
        assert svc.match_repo.create.await_args.kwargs["status"] == "accepted"

    async def test_refused_merge_leaves_a_pending_match(self, monkeypatch) -> None:
        svc = make_service()
        synced, manual = make_txn(sync_id="t-1", sync_source="simplefin"), make_txn(is_split=True)
        svc.txn_repo.find_match_candidates = AsyncMock(return_value=[manual])
        svc.payee_repo.get = AsyncMock(return_value=None)
        svc.txn_service.merge = AsyncMock(
            side_effect=InvariantViolation("Cannot merge away a split")
        )
        monkeypatch.setattr(
            "igab.services.transaction_matching_service.calculate_confidence", lambda *a: 0.95
        )

        await svc.try_match(synced)

        assert svc.match_repo.create.await_args.kwargs["status"] == "pending"

    async def test_below_threshold_is_pending_without_a_merge(self, monkeypatch) -> None:
        svc = make_service()
        synced, manual = make_txn(sync_id="t-1", sync_source="simplefin"), make_txn()
        svc.txn_repo.find_match_candidates = AsyncMock(return_value=[manual])
        svc.payee_repo.get = AsyncMock(return_value=None)
        monkeypatch.setattr(
            "igab.services.transaction_matching_service.calculate_confidence", lambda *a: 0.7
        )

        await svc.try_match(synced)

        svc.txn_service.merge.assert_not_awaited()
        assert svc.match_repo.create.await_args.kwargs["status"] == "pending"


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
        svc.session.execute = AsyncMock(side_effect=[synced_result, manual_result, None, None])

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

    async def test_accept_guard_trip_leaves_match_pending(self) -> None:
        """A blocked merge (structured loser) propagates the error and does
        NOT resolve the match — the user can unreconcile and re-accept."""
        svc = make_service()
        synced = make_txn(sync_id="t-9", cleared="reconciled")
        manual = make_txn(is_split=True)
        match = make_match(synced_id=synced.id, manual_id=manual.id)

        svc.match_repo.get = AsyncMock(return_value=match)
        svc.match_repo.update_status = AsyncMock()
        svc.txn_service.merge = AsyncMock(
            side_effect=InvariantViolation("Cannot merge away a split")
        )

        synced_result = MagicMock()
        synced_result.scalar_one_or_none = MagicMock(return_value=synced)
        manual_result = MagicMock()
        manual_result.scalar_one_or_none = MagicMock(return_value=manual)
        svc.session.execute = AsyncMock(side_effect=[synced_result, manual_result])

        with pytest.raises(InvariantViolation):
            await svc.accept_match(match.id)

        svc.match_repo.update_status.assert_not_awaited()

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
