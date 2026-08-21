"""Phase 3 spec: merge asserts two rows are the same real transaction.
Amounts must match, attachments follow the survivor, pending review matches
die with the deleted row, and bank identity is adopted. The survivor's ledger
date is never rewritten — bank provenance arrives as bank_posted_date."""

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


async def test_merge_keeps_survivor_date_and_inherits_bank_posted_date(db_session):
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

    assert survivor.date == user_day, "the survivor's ledger date is never rewritten"
    assert survivor.entered_date is None, "no date rewrite, no provenance copy"
    assert survivor.bank_posted_date == TODAY, "bank date arrives as metadata instead"



async def test_merge_inherits_bank_amount_and_payee_from_the_bank_row(db_session):
    """The survivor is the user's row; the bank's own figures must survive the
    merge as provenance instead of dying with the deleted row."""
    services, budget, checking = await _setup(db_session)
    manual = await create_transaction(db_session, budget, checking, "-50.00", TODAY)
    synced = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY,
        sync_id="t-bank", sync_source="simplefin",
        bank_amount="-50.00", bank_payee="SHELL OIL",
    )

    survivor = await services.transactions.merge(
        budget.id, [manual.id, synced.id], survivor_id=manual.id
    )

    assert survivor.amount == Decimal("-50.00"), "the user's ledger amount stands"
    assert survivor.bank_amount == Decimal("-50.00")
    assert survivor.bank_payee == "SHELL OIL"
    await assert_financial_invariants(db_session, budget.id)


async def test_merge_falls_back_to_the_bank_rows_own_amount(db_session):
    """A bank row synced before bank_amount existed has none recorded; its
    ledger amount is still the bank's figure and stands in for it."""
    services, budget, checking = await _setup(db_session)
    manual = await create_transaction(db_session, budget, checking, "-50.00", TODAY)
    synced = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY,
        sync_id="t-legacy", sync_source="simplefin",
    )

    survivor = await services.transactions.merge(
        budget.id, [manual.id, synced.id], survivor_id=manual.id
    )

    assert survivor.bank_amount == Decimal("-50.00")


async def test_merge_of_two_manual_rows_records_no_bank_amount(db_session):
    services, budget, checking = await _setup(db_session)
    a = await create_transaction(db_session, budget, checking, "-50.00", TODAY)
    b = await create_transaction(db_session, budget, checking, "-50.00", TODAY)

    survivor = await services.transactions.merge(budget.id, [a.id, b.id], survivor_id=a.id)

    assert survivor.bank_amount is None
    assert survivor.bank_payee is None

async def test_merge_prefers_losers_explicit_bank_posted_date(db_session):
    services, budget, checking = await _setup(db_session)
    posted_day = TODAY - timedelta(days=1)
    manual = await create_transaction(db_session, budget, checking, "-50.00", TODAY)
    synced = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY,
        sync_id="t-3", sync_source="simplefin", bank_posted_date=posted_day,
    )

    survivor = await services.transactions.merge(
        budget.id, [manual.id, synced.id], survivor_id=manual.id
    )

    assert survivor.bank_posted_date == posted_day


async def test_merge_bank_row_survivor_keeps_own_date_with_provenance(db_session):
    """Mirror case: the user picks the bank row as survivor — it keeps its own
    (bank) date and the manual row's date is preserved once in entered_date."""
    services, budget, checking = await _setup(db_session)
    user_day = TODAY - timedelta(days=2)
    manual = await create_transaction(db_session, budget, checking, "-50.00", user_day)
    synced = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY,
        sync_id="t-4", sync_source="simplefin",
    )

    survivor = await services.transactions.merge(
        budget.id, [manual.id, synced.id], survivor_id=synced.id
    )

    assert survivor.id == synced.id
    assert survivor.date == TODAY
    assert survivor.entered_date == user_day, "manual date kept once as provenance"


async def test_merge_idless_bank_loser_confers_identity(db_session):
    """An id-less feed row (sync_source set, sync_id NULL) is still the bank's
    row: the survivor inherits sync_source and posted-date provenance."""
    services, budget, checking = await _setup(db_session)
    manual = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY - timedelta(days=1)
    )
    idless = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, sync_source="simplefin"
    )

    survivor = await services.transactions.merge(
        budget.id, [manual.id, idless.id], survivor_id=manual.id
    )

    assert survivor.id == manual.id
    assert survivor.sync_id is None
    assert survivor.sync_source == "simplefin", "id-less bank identity transfers"
    assert survivor.bank_posted_date == TODAY, "the bank row's date arrives as provenance"
    await assert_financial_invariants(db_session, budget.id)


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
