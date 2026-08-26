"""Phase 3 spec: merge asserts two rows are the same real transaction.
Amounts must match, attachments follow the survivor, pending review matches
die with the deleted row, and bank identity is adopted. The survivor's ledger
date is never rewritten — bank provenance arrives as bank_posted_date."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import ChangeLog, TransactionAttachment
from igab.domain.exceptions import InvariantViolation
from igab.services.transaction_service import TransactionCreate
from igab.services.undo_service import UndoService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
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
        db_session,
        budget,
        checking,
        "-50.00",
        TODAY,
        sync_id="t-1",
        sync_source="simplefin",
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
        db_session,
        budget,
        checking,
        "-50.00",
        TODAY,
        sync_id="t-2",
        sync_source="simplefin",
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
        db_session,
        budget,
        checking,
        "-50.00",
        TODAY,
        sync_id="t-bank",
        sync_source="simplefin",
        bank_amount="-50.00",
        bank_payee="SHELL OIL",
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
        db_session,
        budget,
        checking,
        "-50.00",
        TODAY,
        sync_id="t-legacy",
        sync_source="simplefin",
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
        db_session,
        budget,
        checking,
        "-50.00",
        TODAY,
        sync_id="t-3",
        sync_source="simplefin",
        bank_posted_date=posted_day,
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
        db_session,
        budget,
        checking,
        "-50.00",
        TODAY,
        sync_id="t-4",
        sync_source="simplefin",
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


# ─── One merge: the review queue's accept IS TransactionService.merge ────────
# Each test below is named for a difference the two implementations used to
# have. `_accept` goes through the queue; `merge` is the user's explicit merge.


async def _accept(services, synced, manual):
    match = await services.match_repo.create(
        synced_transaction_id=synced.id, manual_transaction_id=manual.id, confidence_score=0.8
    )
    await services.matching.accept_match(match.id)
    return match


async def _bank_row(db_session, budget, account, amount="-50.00", day=TODAY, **over):
    kwargs = dict(
        cleared="cleared",
        sync_id="t-bank",
        sync_source="simplefin",
        bank_posted_date=day,
        bank_amount=amount,
    )
    kwargs.update(over)
    return await create_transaction(db_session, budget, account, amount, day, **kwargs)


async def _batch_of(db_session, budget_id, entity_id):
    await db_session.flush()
    rows = (
        (
            await db_session.execute(
                select(ChangeLog)
                .where(ChangeLog.budget_id == budget_id, ChangeLog.entity_id == entity_id)
                .order_by(ChangeLog.seq.desc())
            )
        )
        .scalars()
        .all()
    )
    assert rows, "the merge was recorded"
    return rows[0].batch_id


async def _split(services, budget, account, total, legs, *, cleared="uncleared", payee=None):
    header = TransactionCreate(
        account_id=account.id,
        date=TODAY,
        amount=Decimal(total),
        cleared=cleared,
        payee_id=payee.id if payee else None,
    )
    splits = [
        TransactionCreate(account_id=account.id, date=TODAY, amount=Decimal(a), category_id=c)
        for a, c in legs
    ]
    return await services.transactions.create_split(budget.id, header, splits)


async def test_accepting_a_match_reassigns_attachments(db_session):
    """_accept_link soft-deleted the loser and left its receipt on it."""
    services, budget, checking = await _setup(db_session)
    manual = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, cleared="uncleared"
    )
    synced = await _bank_row(db_session, budget, checking)
    _attach(db_session, synced)
    await db_session.flush()

    await _accept(services, synced, manual)

    assert len(await services.attachment_repo.get_for_transaction(manual.id)) == 1
    assert await services.attachment_repo.get_for_transaction(synced.id) == []


async def test_accepting_a_match_is_recorded_and_undoable(db_session):
    """_accept_link wrote raw UPDATEs — no change-log rows, nothing to undo."""
    services, budget, checking = await _setup(db_session)
    manual = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, cleared="uncleared"
    )
    synced = await _bank_row(db_session, budget, checking)

    await _accept(services, synced, manual)
    await db_session.refresh(manual)
    assert manual.cleared == "cleared" and manual.sync_id == "t-bank"

    batch_id = await _batch_of(db_session, budget.id, manual.id)
    await UndoService(db_session).undo_batch(budget.id, batch_id)
    await db_session.refresh(manual)
    await db_session.refresh(synced)
    assert not synced.is_deleted
    assert manual.sync_id is None and manual.cleared == "uncleared"
    await assert_financial_invariants(db_session, budget.id)


async def test_accepting_a_match_cancels_other_pending_matches_on_the_loser(db_session):
    services, budget, checking = await _setup(db_session)
    manual = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, cleared="uncleared"
    )
    other = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, cleared="uncleared"
    )
    synced = await _bank_row(db_session, budget, checking)
    stale = await services.match_repo.create(
        synced_transaction_id=synced.id, manual_transaction_id=other.id, confidence_score=0.6
    )

    await _accept(services, synced, manual)

    assert (await services.match_repo.get(stale.id)).status == "rejected"


async def test_accepting_two_manual_rows_does_not_claim_a_bank_source(db_session):
    """_accept_link stamped has_sync_source on every accept, bank or not."""
    services, budget, checking = await _setup(db_session)
    payee = await create_payee(db_session, budget, "Lunch")
    a = await create_transaction(db_session, budget, checking, "-12.00", TODAY, payee=payee)
    b = await create_transaction(db_session, budget, checking, "-12.00", TODAY, payee=payee)
    assert await services.matching.scan_for_duplicates(checking.id) == 1
    [match] = await services.match_repo.get_pending_for_account(checking.id)

    await services.matching.accept_match(match.id)

    await db_session.refresh(a)
    await db_session.refresh(b)
    survivor = a if not a.is_deleted else b
    assert not survivor.is_deleted
    assert survivor.has_sync_source is False and survivor.sync_source is None


async def test_accept_used_to_skip_entered_date_on_a_bank_survivor(db_session):
    services, budget, checking = await _setup(db_session)
    user_day = TODAY - timedelta(days=2)
    manual = await create_transaction(
        db_session, budget, checking, "-50.00", user_day, cleared="uncleared"
    )
    synced = await _bank_row(db_session, budget, checking, cleared="reconciled")

    await _accept(services, synced, manual)

    await db_session.refresh(synced)
    assert not synced.is_deleted, "reconciled survives"
    assert synced.entered_date == user_day, "the user's date is kept once as provenance"


async def test_merge_used_to_reject_a_split_parent_survivor(db_session):
    services, budget, checking = await _setup(db_session)
    parent = await _split(
        services, budget, checking, "-88.00", [("-50.00", None), ("-38.00", None)]
    )
    synced = await _bank_row(db_session, budget, checking, amount="-88.00")

    survivor = await services.transactions.merge(budget.id, [synced.id, parent.id])

    assert survivor.id == parent.id and survivor.sync_id == "t-bank"
    assert len(await services.transaction_repo.get_splits(parent.id)) == 2
    await assert_financial_invariants(db_session, budget.id)


async def test_merge_used_to_reject_a_transfer_leg_survivor(db_session):
    services, budget, checking = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")
    leg = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("-150.00"),
            cleared="uncleared",
            transfer_account_id=savings.id,
        ),
    )
    synced = await _bank_row(db_session, budget, checking, amount="-150.00")

    survivor = await services.transactions.merge(budget.id, [synced.id, leg.id])

    assert survivor.id == leg.id and survivor.sync_id == "t-bank"
    partner = await services.transaction_repo.get(leg.transfer_id)
    assert partner is not None and not partner.is_deleted
    await assert_financial_invariants(db_session, budget.id)


async def test_merge_used_to_leave_the_survivor_uncleared_after_a_posted_bank_loser(db_session):
    """merge never wrote `cleared`; _accept_link did. One rule now: a posted
    bank loser clears an uncleared survivor, and a split's lines follow."""
    services, budget, checking = await _setup(db_session)
    parent = await _split(
        services, budget, checking, "-88.00", [("-50.00", None), ("-38.00", None)]
    )
    synced = await _bank_row(db_session, budget, checking, amount="-88.00")

    survivor = await services.transactions.merge(
        budget.id, [synced.id, parent.id], survivor_id=parent.id
    )

    assert survivor.cleared == "cleared"
    assert all(
        c.cleared == "cleared" for c in await services.transaction_repo.get_splits(parent.id)
    )


async def test_merge_refuses_a_structured_loser(db_session):
    services, budget, checking = await _setup(db_session)
    reconciled = await _bank_row(
        db_session, budget, checking, amount="-88.00", cleared="reconciled"
    )
    parent = await _split(
        services, budget, checking, "-88.00", [("-50.00", None), ("-38.00", None)]
    )

    with pytest.raises(InvariantViolation, match="merge away a split"):
        await services.transactions.merge(budget.id, [reconciled.id, parent.id])
    await db_session.refresh(parent)
    assert not parent.is_deleted


async def test_merge_refuses_the_flat_row_as_survivor_over_a_split_parent(db_session):
    services, budget, checking = await _setup(db_session)
    parent = await _split(
        services, budget, checking, "-88.00", [("-50.00", None), ("-38.00", None)]
    )
    flat = await create_transaction(db_session, budget, checking, "-88.00", TODAY)

    with pytest.raises(InvariantViolation, match="must be kept as the survivor"):
        await services.transactions.merge(budget.id, [flat.id, parent.id], survivor_id=flat.id)


async def test_merge_fills_memo_category_payee_and_approval_the_survivor_lacks(db_session):
    services, budget, checking = await _setup(db_session)
    group = await create_category_group(db_session, budget)
    cat = await create_category(db_session, budget, group, "Groceries")
    payee = await create_payee(db_session, budget, "Corner Market")
    bare = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, cleared="uncleared", approved=False
    )
    rich = await _bank_row(
        db_session, budget, checking, memo="from the bank", category=cat, payee=payee, approved=True
    )

    survivor = await services.transactions.merge(budget.id, [bare.id, rich.id], survivor_id=bare.id)

    assert survivor.memo == "from the bank"
    assert survivor.category_id == cat.id and survivor.payee_id == payee.id
    assert survivor.approved is True


async def test_merge_appends_a_differing_memo(db_session):
    services, budget, checking = await _setup(db_session)
    a = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, memo="lunch with Sam"
    )
    b = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, memo="split the bill"
    )

    survivor = await services.transactions.merge(budget.id, [a.id, b.id], survivor_id=a.id)

    assert survivor.memo == "lunch with Sam — split the bill"


async def test_merge_never_fills_category_or_payee_onto_a_transfer_leg(db_session):
    services, budget, checking = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")
    group = await create_category_group(db_session, budget)
    cat = await create_category(db_session, budget, group, "Groceries")
    leg = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("-150.00"),
            cleared="uncleared",
            transfer_account_id=savings.id,
        ),
    )
    synced = await _bank_row(db_session, budget, checking, amount="-150.00", category=cat)

    survivor = await services.transactions.merge(budget.id, [synced.id, leg.id])

    assert survivor.id == leg.id
    assert survivor.category_id is None
    assert survivor.payee_id == leg.payee_id, "a transfer leg's payee is its destination"


async def test_accepting_amount_change_review_applies_bank_amount_and_records_entered_amount(
    db_session,
):
    """The bank posted -60 against the user's -50 (a tip). Accepting the
    review is the one path that changes a user-entered amount."""
    services, budget, checking = await _setup(db_session)
    manual = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, cleared="uncleared"
    )
    synced = await _bank_row(db_session, budget, checking, amount="-60.00")

    await _accept(services, synced, manual)

    await db_session.refresh(manual)
    assert manual.amount == Decimal("-60.00")
    assert manual.entered_amount == Decimal("-50.00")
    assert manual.cleared == "cleared" and manual.sync_id == "t-bank"
    assert await services.account_repo.get_balance(checking.id) == Decimal("-60.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_rejecting_amount_change_review_leaves_user_row_uncleared_and_unlinked(db_session):
    services, budget, checking = await _setup(db_session)
    manual = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, cleared="uncleared"
    )
    synced = await _bank_row(db_session, budget, checking, amount="-60.00")
    match = await services.match_repo.create(
        synced_transaction_id=synced.id, manual_transaction_id=manual.id, confidence_score=0.6
    )

    await services.matching.reject_match(match.id)

    await db_session.refresh(manual)
    assert manual.amount == Decimal("-50.00") and manual.cleared == "uncleared"
    assert manual.sync_id is None
    await db_session.refresh(synced)
    assert not synced.is_deleted


async def test_split_parent_amount_change_accept_refused_until_lines_match(db_session):
    services, budget, checking = await _setup(db_session)
    parent = await _split(
        services, budget, checking, "-50.00", [("-30.00", None), ("-20.00", None)]
    )
    synced = await _bank_row(db_session, budget, checking, amount="-60.00")
    match = await services.match_repo.create(
        synced_transaction_id=synced.id, manual_transaction_id=parent.id, confidence_score=0.7
    )

    with pytest.raises(InvariantViolation, match="adjust the lines"):
        await services.matching.accept_match(match.id)

    assert (await services.match_repo.get(match.id)).status == "pending"
    await db_session.refresh(parent)
    assert parent.amount == Decimal("-50.00") and not parent.is_deleted


async def test_undo_of_an_accept_with_a_reconciled_keeper_restores_both_rows(db_session):
    """Undo of the batch touches the reconciled keeper's provenance only —
    which the lock rule allows — and brings the loser back."""
    services, budget, checking = await _setup(db_session)
    keeper = await create_transaction(
        db_session, budget, checking, "-50.00", TODAY, cleared="reconciled"
    )
    synced = await _bank_row(db_session, budget, checking)

    await _accept(services, synced, keeper)
    await db_session.refresh(keeper)
    assert keeper.sync_id == "t-bank" and keeper.cleared == "reconciled"

    batch_id = await _batch_of(db_session, budget.id, keeper.id)
    await UndoService(db_session).undo_batch(budget.id, batch_id)
    await db_session.refresh(keeper)
    await db_session.refresh(synced)
    assert keeper.sync_id is None and keeper.cleared == "reconciled"
    assert not synced.is_deleted


async def test_accept_and_manual_merge_produce_the_same_survivor(db_session):
    """Differential pin: the queue's accept and the explicit merge are one
    implementation, so the same pair ends the same way either route."""
    services, budget, checking = await _setup(db_session)
    fields = (
        "id",
        "cleared",
        "sync_id",
        "sync_source",
        "has_sync_source",
        "bank_posted_date",
        "bank_amount",
        "amount",
        "date",
        "memo",
        "category_id",
        "payee_id",
    )

    async def pair(tag):
        manual = await create_transaction(
            db_session,
            budget,
            checking,
            "-50.00",
            TODAY - timedelta(days=1),
            cleared="uncleared",
            memo=f"{tag} memo",
        )
        synced = await _bank_row(db_session, budget, checking, sync_id=f"t-{tag}")
        return manual, synced

    m1, s1 = await pair("accept")
    await _accept(services, s1, m1)
    m2, s2 = await pair("merge")
    await services.transactions.merge(budget.id, [s2.id, m2.id])

    await db_session.refresh(m1)
    await db_session.refresh(m2)
    left = {f: getattr(m1, f) for f in fields if f not in ("id", "sync_id", "memo")}
    right = {f: getattr(m2, f) for f in fields if f not in ("id", "sync_id", "memo")}
    assert left == right
    assert not m1.is_deleted and not m2.is_deleted
