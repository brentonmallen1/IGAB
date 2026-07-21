"""Phase 3 spec: merge asserts two rows are the same real transaction.
Amounts must match, attachments follow the survivor, pending review matches
die with the deleted row, and bank identity (with its date) is adopted."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.db.models import TransactionAttachment
from igab.domain.exceptions import InvariantViolation

from .factories import (
    create_account,
    create_budget,
    create_transaction,
    create_user,
    make_services,
)
from .invariants import assert_financial_invariants

TODAY = date(2026, 7, 10)


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    return services, budget, checking


def _attach(db_session, txn, name="receipt.jpg"):
    attachment = TransactionAttachment(
        transaction_id=txn.id,
        filename=name,
        original_filename=name,
        content_type="image/jpeg",
        file_size=1234,
    )
    db_session.add(attachment)
    return attachment


async def test_merge_unequal_amounts_rejected(db_session):
    services, budget, checking = await _setup(db_session)
    a = await create_transaction(db_session, budget, checking, "-50.00", TODAY)
    b = await create_transaction(db_session, budget, checking, "-49.00", TODAY)

    with pytest.raises(InvariantViolation, match="identical amounts"):
        await services.transactions.merge(budget.id, [a.id, b.id])

    balance = await services.account_repo.get_balance(checking.id)
    assert balance == Decimal("-99.00"), "failed merge must not move money"


async def test_merge_moves_attachments_and_cancels_matches(db_session):
    services, budget, checking = await _setup(db_session)
    manual = await create_transaction(db_session, budget, checking, "-50.00", TODAY)
    synced = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY,
        sync_id="t-1", sync_source="simplefin",
    )
    _attach(db_session, synced)
    await db_session.flush()
    match = await services.match_repo.create(
        synced_transaction_id=synced.id,
        manual_transaction_id=manual.id,
        confidence_score=0.7,
    )

    survivor = await services.transactions.merge(
        budget.id, [manual.id, synced.id], survivor_id=manual.id
    )

    assert survivor.id == manual.id
    assert survivor.sync_id == "t-1"
    attachments = await services.attachment_repo.get_for_transaction(manual.id)
    assert len(attachments) == 1, "attachment must follow the survivor"
    refreshed_match = await services.match_repo.get(match.id)
    assert refreshed_match.status == "rejected", "pending match dies with the merge"
    await assert_financial_invariants(db_session, budget.id)


async def test_merge_adopts_bank_date_with_provenance(db_session):
    services, budget, checking = await _setup(db_session)
    user_day = TODAY - timedelta(days=2)
    manual = await create_transaction(db_session, budget, checking, "-50.00", user_day)
    synced = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY,
        sync_id="t-2", sync_source="simplefin",
    )

    survivor = await services.transactions.merge(
        budget.id, [manual.id, synced.id], survivor_id=manual.id
    )

    assert survivor.date == TODAY, "ledger aligns to the bank posted date"
    assert survivor.entered_date == user_day, "user's date preserved as metadata"


async def test_merge_conflicting_sync_ids_rejected(db_session):
    services, budget, checking = await _setup(db_session)
    a = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, sync_id="t-a", sync_source="simplefin"
    )
    b = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, sync_id="t-b", sync_source="simplefin"
    )

    with pytest.raises(InvariantViolation, match="different bank"):
        await services.transactions.merge(budget.id, [a.id, b.id])


async def test_merge_reconciled_must_survive(db_session):
    services, budget, checking = await _setup(db_session)
    reconciled = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, cleared="reconciled"
    )
    other = await create_transaction(db_session, budget, checking, "-50.00", TODAY)

    with pytest.raises(InvariantViolation, match="survivor"):
        await services.transactions.merge(
            budget.id, [reconciled.id, other.id], survivor_id=other.id
        )

    survivor = await services.transactions.merge(budget.id, [reconciled.id, other.id])
    assert survivor.id == reconciled.id
