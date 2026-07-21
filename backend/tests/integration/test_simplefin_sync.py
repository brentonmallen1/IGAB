"""Phase 2 spec: SimpleFIN sync dedup, pending→posted, entered_date, and the
accept-match flow — all against a real database.

Bank data wins on every link path: posted amount/date/cleared replace the
provisional values, and whenever a date is overwritten the prior date is
preserved once in entered_date.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from igab.db.models import Transaction
from igab.domain.exceptions import InvariantViolation
from igab.services.simplefin_service import SimpleFINService

from .factories import (
    create_account,
    create_budget,
    create_simplefin_connection,
    create_transaction,
    create_user,
    make_services,
)

SF_ACCT = "sf-acct-1"


class FakeClient:
    def __init__(self, payload: list[dict]):
        self.payload = payload

    async def get_transactions(self, access_url: str, since=None) -> list[dict]:
        return self.payload

    async def get_accounts(self, access_url: str) -> list[dict]:
        return []


def _ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 12, tzinfo=UTC).timestamp())


def bank_txn(
    txn_id: str | None,
    amount: str,
    on: date,
    *,
    posted: bool = True,
    payee: str = "CORNER MARKET",
) -> dict:
    t: dict = {
        "account_id": SF_ACCT,
        "amount": amount,
        "payee": payee,
        "description": f"{payee} POS PURCHASE",
    }
    if txn_id is not None:
        t["id"] = txn_id
    if posted:
        t["posted"] = _ts(on)
    else:
        t["posted"] = 0
        t["transacted_at"] = _ts(on)
    return t


async def _sync_setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(
        db_session, budget, "Checking", simplefin_account_id=SF_ACCT
    )
    conn = await create_simplefin_connection(db_session, user)
    return services, user, budget, account, conn


def _service(services, payload: list[dict]) -> SimpleFINService:
    svc = SimpleFINService(
        session=services.session,
        repo=services.simplefin_repo,
        account_repo=services.account_repo,
        txn_repo=services.transaction_repo,
        txn_service=services.transactions,
        matching_service=services.matching,
    )
    svc.client = FakeClient(payload)
    return svc


async def _live_rows(db_session, account_id) -> list[Transaction]:
    rows = (
        (
            await db_session.execute(
                select(Transaction).where(
                    Transaction.account_id == account_id,
                    Transaction.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


PATCH_DECRYPT = patch(
    "igab.services.simplefin_service.decrypt", return_value="https://u:p@x.test"
)


async def test_sync_idempotent_same_payload_twice(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [
        bank_txn("t-1", "-12.50", today - timedelta(days=1)),
        bank_txn("t-2", "-40.00", today),
    ]
    svc = _service(services, payload)

    with PATCH_DECRYPT:
        first = await svc.sync(conn.id, budget.id)
        second = await svc.sync(conn.id, budget.id)

    assert first.get("error") is None, first
    assert first["imported"] == 2
    assert second["imported"] == 0
    assert len(await _live_rows(db_session, account.id)) == 2


async def test_pending_to_posted_updates_amount_date_cleared(db_session):
    """The classic tip scenario: -20.00 auth posts as -23.50 a day later."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    auth_day = date.today() - timedelta(days=2)
    post_day = date.today() - timedelta(days=1)

    svc = _service(services, [bank_txn("t-9", "-20.00", auth_day, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)

    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1
    assert rows[0].cleared == "pending"
    assert await services.account_repo.get_balance(account.id) == Decimal("0")

    svc.client = FakeClient([bank_txn("t-9", "-23.50", post_day, posted=True)])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1, "pending→posted must update in place, not duplicate"
    txn = rows[0]
    assert txn.cleared == "cleared"
    assert txn.amount == Decimal("-23.50")
    assert txn.date == post_day
    assert txn.entered_date == auth_day, "prior date preserved as provenance"
    assert result["cleared"] == 1
    assert await services.account_repo.get_balance(account.id) == Decimal("-23.50")


async def test_fuzzy_automatch_adopts_bank_date_and_preserves_entered_date(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    user_day = date.today() - timedelta(days=3)
    bank_day = date.today() - timedelta(days=1)

    payee = await services.payee_repo.find_or_create(budget.id, "Corner Market")
    manual = await create_transaction(
        db_session, budget, account, "-50.00", user_day, payee=payee, cleared="uncleared"
    )

    svc = _service(services, [bank_txn("t-77", "-50.00", bank_day, payee="CORNER MARKET #12")])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 0, "high-confidence match must attach, not import"
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1
    txn = rows[0]
    assert txn.id == manual.id
    assert txn.sync_id == "t-77"
    assert txn.sync_source == "simplefin"
    assert txn.date == bank_day, "ledger aligns to the bank posted date"
    assert txn.entered_date == user_day, "user's entered date kept as metadata"
    assert txn.cleared == "cleared"


async def test_two_distinct_same_day_same_amount_bank_txns_import_as_two(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [
        bank_txn("t-a", "-5.75", today, payee="STARBUCKS #111"),
        bank_txn("t-b", "-5.75", today, payee="STARBUCKS #111"),
    ]
    svc = _service(services, payload)
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 2
    assert len(await _live_rows(db_session, account.id)) == 2


async def test_missing_bank_id_does_not_false_dedup(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [
        bank_txn(None, "-10.00", today, payee="ALPHA STORE"),
        bank_txn(None, "-99.00", today, payee="BETA STORE"),
    ]
    svc = _service(services, payload)
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 2, "id-less rows must never dedup against each other"
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 2
    assert all(r.sync_id is None for r in rows)


async def test_near_miss_creates_review_match_then_accept_no_reimport_loop(db_session):
    """The accept-link regression reproducer: after accepting a review match,
    re-syncing the same payload must not re-import the bank transaction."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    user_day = date.today() - timedelta(days=1)

    # Manual txn without payee → similarity is neutral 0.5 → score lands in
    # the review band deterministically (0.2*date + 0.4).
    manual = await create_transaction(
        db_session, budget, account, "-80.00", user_day, cleared="uncleared"
    )

    payload = [bank_txn("t-55", "-80.00", user_day, payee="MYSTERY VENDOR")]
    svc = _service(services, payload)
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 1, "review-band match imports and asks the user"
    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 2

    matches = await services.match_repo.get_pending_for_account(account.id)
    assert len(matches) == 1
    match = matches[0]

    await services.matching.accept_match(match.id)

    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1, "accepting merges the pair down to one live row"
    keeper = rows[0]
    assert keeper.id == manual.id
    assert keeper.sync_id == "t-55", "bank identity must survive the merge"
    assert keeper.has_sync_source is True
    assert keeper.cleared == "cleared"

    with PATCH_DECRYPT:
        again = await svc.sync(conn.id, budget.id)
    assert again["imported"] == 0, "sync_id on the keeper prevents the reimport loop"
    assert len(await _live_rows(db_session, account.id)) == 1


async def test_accept_keeps_reconciled_side(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()

    reconciled = await create_transaction(
        db_session, budget, account, "-30.00", today - timedelta(days=2), cleared="reconciled"
    )
    newer = await create_transaction(
        db_session, budget, account, "-30.00", today, cleared="cleared", sync_id="t-x",
        sync_source="simplefin",
    )
    match = await services.match_repo.create(
        synced_transaction_id=reconciled.id,
        manual_transaction_id=newer.id,
        confidence_score=0.7,
    )

    await services.matching.accept_match(match.id)

    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1
    keeper = rows[0]
    assert keeper.id == reconciled.id, "the reconciled row must never be deleted"
    assert keeper.cleared == "reconciled"
    assert keeper.sync_id == "t-x", "bank identity copied onto the reconciled keeper"


async def test_accept_both_reconciled_rejected(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    a = await create_transaction(
        db_session, budget, account, "-30.00", today, cleared="reconciled"
    )
    b = await create_transaction(
        db_session, budget, account, "-30.00", today - timedelta(days=1), cleared="reconciled"
    )
    match = await services.match_repo.create(
        synced_transaction_id=a.id, manual_transaction_id=b.id, confidence_score=0.6
    )

    with pytest.raises(InvariantViolation):
        await services.matching.accept_match(match.id)

    assert len(await _live_rows(db_session, account.id)) == 2


async def test_stale_pending_swept_when_absent_from_feed(db_session):
    """Bank dropped an auth (or re-identified it at posting): the phantom
    pending row must not linger forever."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    auth_day = date.today() - timedelta(days=2)

    svc = _service(services, [bank_txn("t-old", "-15.00", auth_day, posted=False)])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)
    assert len(await _live_rows(db_session, account.id)) == 1

    # Next sync: the auth vanished; a differently-identified posted txn with a
    # different amount appears (classic id-change-at-posting).
    svc.client = FakeClient([bank_txn("t-new", "-17.00", date.today(), posted=True)])
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    rows = await _live_rows(db_session, account.id)
    assert len(rows) == 1, "stale pending swept; posted row imported"
    assert rows[0].sync_id == "t-new"
    assert rows[0].amount == Decimal("-17.00")
    assert result.get("removed_pending") == 1


async def test_manual_pending_rows_not_swept(db_session):
    """The sweep only touches sync-created pendings, never user rows."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    manual_pending = await create_transaction(
        db_session, budget, account, "-33.00", date.today(), cleared="pending"
    )
    assert manual_pending.sync_source is None

    svc = _service(services, [bank_txn("t-z", "-1.00", date.today())])
    with PATCH_DECRYPT:
        await svc.sync(conn.id, budget.id)

    rows = await _live_rows(db_session, account.id)
    ids = {r.id for r in rows}
    assert manual_pending.id in ids, "manual pending row must survive the sweep"


async def test_duplicate_sync_id_within_one_payload_imports_once(db_session):
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    payload = [
        bank_txn("t-dup", "-8.00", today),
        bank_txn("t-dup", "-8.00", today),
    ]
    svc = _service(services, payload)
    with PATCH_DECRYPT:
        result = await svc.sync(conn.id, budget.id)

    assert result["imported"] == 1
    assert len(await _live_rows(db_session, account.id)) == 1


async def test_unique_index_blocks_duplicate_live_sync_id(db_session):
    """DB-level backstop: two live rows with the same (account, sync_id) are
    impossible; a soft-deleted duplicate is allowed."""
    services, user, budget, account, conn = await _sync_setup(db_session)
    today = date.today()
    await create_transaction(
        db_session, budget, account, "-1.00", today, sync_id="dup-1", sync_source="simplefin"
    )
    await create_transaction(
        db_session, budget, account, "-2.00", today, sync_id="dup-1",
        sync_source="simplefin", is_deleted=True,
    )

    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await create_transaction(
            db_session, budget, account, "-3.00", today, sync_id="dup-1",
            sync_source="simplefin",
        )
