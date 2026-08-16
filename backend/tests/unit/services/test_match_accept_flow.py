"""
Unit tests for TransactionMatchingService accept/reject flows.

Match acceptance rules (full DB behavior verified in
tests/integration/test_simplefin_sync.py — these unit tests cover the
mock-testable guards and control flow):
  1. The pair merges down to one live row: the keeper inherits the loser's
     bank identity (sync_id/sync_source, import metadata) and the loser is
     soft-deleted FIRST (unique-index-safe ordering).
  2. A reconciled row always wins the keeper role; after that a structured
     row (split parent / transfer leg) beats a flat one. A structured loser
     raises before anything is mutated — never orphan split children or a
     transfer partner.
  3. A match whose sides are missing or already deleted is auto-rejected.
  4. Re-accepting an accepted match is a no-op; a self-match is a no-op.
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
    t.payee_id = None
    t.budget_id = BUDGET_ID
    t.date = txn_date
    t.entered_date = None
    return t


def _statement_params(call) -> dict:
    """Bound parameter values of a captured SQLAlchemy statement."""
    return call.args[0].compile().params


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


class TestStructuredRowGuards:
    """A split parent or transfer leg must never be the merged-away side."""

    async def test_split_parent_loser_raises_without_mutation(self) -> None:
        # Reconciled flat synced row wins the keeper role, which would make
        # the manual split parent the loser — refuse instead of orphaning
        # its children in category activity.
        svc = make_service()
        synced = make_txn(sync_id="t-1", cleared="reconciled")
        manual = make_txn(is_split=True)

        with pytest.raises(InvariantViolation, match="split"):
            await svc._accept_link(synced, manual, 0.9)

        svc.session.execute.assert_not_awaited()

    async def test_transfer_leg_loser_raises_without_mutation(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-1", cleared="reconciled")
        manual = make_txn(transfer_id=uuid.uuid4())

        with pytest.raises(InvariantViolation, match="transfer"):
            await svc._accept_link(synced, manual, 0.9)

        svc.session.execute.assert_not_awaited()

    async def test_both_structured_raises(self) -> None:
        svc = make_service()
        synced = make_txn(is_split=True)
        manual = make_txn(transfer_id=uuid.uuid4())

        with pytest.raises(InvariantViolation):
            await svc._accept_link(synced, manual, 0.9)

        svc.session.execute.assert_not_awaited()

    async def test_split_child_on_either_side_raises(self) -> None:
        svc = make_service()
        child = make_txn(parent_transaction_id=uuid.uuid4())
        flat = make_txn(sync_id="t-1")

        with pytest.raises(InvariantViolation, match="split line"):
            await svc._accept_link(child, flat, 0.9)
        with pytest.raises(InvariantViolation, match="split line"):
            await svc._accept_link(flat, child, 0.9)

        svc.session.execute.assert_not_awaited()

    async def test_structured_synced_row_wins_keeper_role(self) -> None:
        """A structured synced row beats a flat manual row: the flat side is
        deleted and the split parent absorbs the bank identity."""
        svc = make_service()
        synced = make_txn(is_split=True)
        manual = make_txn(sync_id="t-1", sync_source="simplefin", cleared="cleared")

        await svc._accept_link(synced, manual, 0.9)

        calls = svc.session.execute.call_args_list
        assert len(calls) == 2
        delete_params = _statement_params(calls[0])
        update_params = _statement_params(calls[1])
        assert manual.id in delete_params.values(), "flat manual row is the loser"
        assert synced.id in update_params.values(), "split parent is the keeper"
        assert update_params.get("sync_id") == "t-1"

    async def test_structured_manual_row_stays_default_keeper(self) -> None:
        """The auto-match path: fresh flat synced row vs manual split parent
        keeps the split parent, as before."""
        svc = make_service()
        synced = make_txn(sync_id="t-1", sync_source="simplefin", cleared="cleared")
        manual = make_txn(is_split=True)

        await svc._accept_link(synced, manual, 0.9)

        calls = svc.session.execute.call_args_list
        assert len(calls) == 2
        assert synced.id in _statement_params(calls[0]).values()
        assert manual.id in _statement_params(calls[1]).values()


class TestBankIdentityInheritance:
    async def test_idless_bank_loser_confers_identity_and_provenance(self) -> None:
        """An id-less feed row (sync_source, no sync_id) is still the bank
        side: the keeper gains sync_source, bank_posted_date, and the
        cleared upgrade."""
        svc = make_service()
        posted = datetime.date(2026, 8, 10)
        synced = make_txn(sync_source="simplefin", cleared="cleared", txn_date=posted)
        manual = make_txn(cleared="uncleared")

        await svc._accept_link(synced, manual, 0.9)

        update_params = _statement_params(svc.session.execute.call_args_list[1])
        assert update_params.get("sync_source") == "simplefin"
        assert update_params.get("bank_posted_date") == posted
        assert update_params.get("cleared") == "cleared"
        assert update_params.get("has_sync_source") is True

    async def test_keeper_with_own_sync_source_is_not_relabeled(self) -> None:
        svc = make_service()
        synced = make_txn(sync_source="simplefin", cleared="cleared")
        manual = make_txn(sync_source="csv")

        await svc._accept_link(synced, manual, 0.9)

        update_params = _statement_params(svc.session.execute.call_args_list[1])
        assert "sync_source" not in update_params

    async def test_manual_loser_confers_no_bank_provenance(self) -> None:
        svc = make_service()
        synced = make_txn(cleared="reconciled", sync_id="t-1")
        manual = make_txn(cleared="cleared", txn_date=datetime.date(2026, 8, 1))

        await svc._accept_link(synced, manual, 0.9)

        update_params = _statement_params(svc.session.execute.call_args_list[1])
        assert "bank_posted_date" not in update_params
        assert "cleared" not in update_params


class TestClearedPropagationToChildren:
    async def test_split_keeper_cleared_upgrade_propagates(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-1", sync_source="simplefin", cleared="cleared")
        manual = make_txn(is_split=True, cleared="uncleared")

        await svc._accept_link(synced, manual, 0.9)

        svc.txn_repo.set_children_cleared.assert_awaited_once_with(manual.id, "cleared")

    async def test_flat_keeper_does_not_touch_children(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-1", sync_source="simplefin", cleared="cleared")
        manual = make_txn(cleared="uncleared")

        await svc._accept_link(synced, manual, 0.9)

        svc.txn_repo.set_children_cleared.assert_not_awaited()

    async def test_no_cleared_upgrade_means_no_child_update(self) -> None:
        svc = make_service()
        synced = make_txn(sync_id="t-1", sync_source="simplefin", cleared="uncleared")
        manual = make_txn(is_split=True, cleared="uncleared")

        await svc._accept_link(synced, manual, 0.9)

        svc.txn_repo.set_children_cleared.assert_not_awaited()


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

    async def test_accept_guard_trip_leaves_match_pending(self) -> None:
        """A blocked merge (structured loser) propagates the error and does
        NOT resolve the match — the user can unreconcile and re-accept."""
        svc = make_service()
        synced = make_txn(sync_id="t-9", cleared="reconciled")
        manual = make_txn(is_split=True)
        match = make_match(synced_id=synced.id, manual_id=manual.id)

        svc.match_repo.get = AsyncMock(return_value=match)
        svc.match_repo.update_status = AsyncMock()

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
