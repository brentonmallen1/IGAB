"""Whether a row the bank stopped reporting is still news — every branch of
`domain.bank_absence`, one line each."""

import uuid
from datetime import date
from decimal import Decimal

from igab.domain.bank_absence import (
    DELETE,
    HOLD,
    KEPT,
    LINKED_TO_HOLD,
    POSTED,
    REMOVED,
    REPORTED_AGAIN,
    RESTORE,
    Absence,
    RowNow,
    action_for,
    is_open,
    latest_by_row,
    offered_action,
    unreported_postings,
)

ROW = uuid.uuid4()


def entry(kind: str, action: str, *, row: uuid.UUID = ROW, sync_id: str | None = "t-1"):
    return Absence(
        transaction_id=row,
        account_id=uuid.uuid4(),
        date=date(2026, 9, 14),
        payee="Harborstone Inn",
        amount=Decimal("-120.00"),
        sync_id=sync_id,
        kind=kind,
        action=action,
    )


def now(*, deleted=False, sync_id=None, cleared="uncleared", undone=False) -> RowNow:
    return RowNow(is_deleted=deleted, sync_id=sync_id, cleared=cleared, removal_undone=undone)


class TestWhatASyncDoes:
    def test_only_a_hold_the_sync_wrote_is_removed(self):
        assert action_for(HOLD) == REMOVED
        assert action_for(LINKED_TO_HOLD) == KEPT
        assert action_for(POSTED) == KEPT


class TestRecordRoundTrip:
    def test_an_entry_survives_the_run_record(self):
        e = entry(HOLD, REMOVED)
        assert Absence.from_record(e.to_record()) == e


class TestRemovedHold:
    def test_listed_while_removed(self):
        assert is_open(entry(HOLD, REMOVED), now(deleted=True), set())

    def test_not_listed_once_restored(self):
        assert not is_open(entry(HOLD, REMOVED), now(deleted=False), set())

    def test_not_listed_when_restored_then_deleted_by_the_person(self):
        assert not is_open(entry(HOLD, REMOVED), now(deleted=True, undone=True), set())

    def test_not_listed_when_the_bank_reports_the_id_again(self):
        assert not is_open(entry(HOLD, REMOVED), now(deleted=True), {"t-1"})

    def test_offers_restore(self):
        assert offered_action(entry(HOLD, REMOVED), now(deleted=True)) == RESTORE


class TestKeptRow:
    def test_a_row_typed_against_a_hold_is_listed_while_unlinked(self):
        assert is_open(entry(LINKED_TO_HOLD, KEPT), now(), set())

    def test_not_listed_once_a_posting_claims_it(self):
        assert not is_open(entry(LINKED_TO_HOLD, KEPT), now(sync_id="t-late"), set())

    def test_not_listed_once_deleted(self):
        assert not is_open(entry(LINKED_TO_HOLD, KEPT), now(deleted=True), set())

    def test_a_posted_row_is_listed_while_it_holds_the_missing_id(self):
        assert is_open(entry(POSTED, KEPT), now(sync_id="t-1", cleared="cleared"), set())

    def test_a_posted_row_that_adopted_a_new_id_is_not_listed(self):
        assert not is_open(entry(POSTED, KEPT), now(sync_id="t-2", cleared="cleared"), set())

    def test_reported_again_closes_it(self):
        assert not is_open(entry(POSTED, REPORTED_AGAIN), now(sync_id="t-1"), set())

    def test_a_gone_row_is_never_listed(self):
        assert not is_open(entry(POSTED, KEPT), None, set())

    def test_offers_delete_unless_reconciled(self):
        assert offered_action(entry(POSTED, KEPT), now(cleared="cleared")) == DELETE
        assert offered_action(entry(POSTED, KEPT), now(cleared="reconciled")) is None


class TestNewsOnce:
    def test_the_newest_entry_per_row_wins(self):
        first, second = entry(POSTED, KEPT), entry(POSTED, REPORTED_AGAIN)
        assert latest_by_row([first, second]) == {ROW: second}

    def test_a_posted_row_still_missing_is_not_recorded_again(self):
        assert unreported_postings([entry(POSTED, KEPT)]) == {ROW}

    def test_a_posted_row_reported_again_may_be_recorded_again(self):
        assert unreported_postings([entry(POSTED, KEPT), entry(POSTED, REPORTED_AGAIN)]) == set()

    def test_holds_and_typed_rows_are_never_held_back(self):
        assert unreported_postings([entry(HOLD, REMOVED), entry(LINKED_TO_HOLD, KEPT)]) == set()
