"""Structured-row guards on the duplicate-match accept path.

Accepting a match merges two rows down to one. The keeper must always be the
structured row (split parent or transfer leg): soft-deleting a split parent
orphans its live children — they keep feeding category activity, double-
counting spending — and soft-deleting a transfer leg strands its partner,
breaking zero-sum. A reconciled row still outranks structure for the keeper
role; when that leaves a structured row as the loser, the accept must raise
and mutate nothing, leaving the match pending for the user to resolve.

Every scenario ends by re-asserting the golden financial invariants.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import Transaction
from igab.domain.exceptions import InvariantViolation

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


async def _make_split(
    db_session, budget, account, day, total, legs, *, cleared="cleared", payee=None
):
    """legs: list of (amount, category | None) child rows."""
    parent = await create_transaction(
        db_session, budget, account, total, day, payee=payee, cleared=cleared, is_split=True
    )
    children = []
    for amount, category in legs:
        children.append(
            await create_transaction(
                db_session,
                budget,
                account,
                amount,
                day,
                parent_transaction_id=parent.id,
                category=category,
                cleared=cleared,
            )
        )
    return parent, children


async def _make_transfer(db_session, budget, from_account, to_account, amount, day):
    out_leg = await create_transaction(
        db_session, budget, from_account, f"-{amount}", day, cleared="cleared"
    )
    in_leg = await create_transaction(
        db_session, budget, to_account, amount, day, cleared="cleared", transfer_id=out_leg.id
    )
    out_leg.transfer_id = in_leg.id
    await db_session.flush()
    return out_leg, in_leg


async def _row(db_session, txn_id) -> Transaction:
    return (
        await db_session.execute(select(Transaction).where(Transaction.id == txn_id))
    ).scalar_one()


async def test_scan_accept_keeps_split_parent_and_category_activity(db_session):
    """The orphaned-children regression: the split parent is the NEWER row, so
    the scan casts it as the 'synced' side — the old default would have soft-
    deleted it, leaving live children double-counting category activity."""
    services, budget, checking = await _setup(db_session)
    group = await create_category_group(db_session, budget)
    groceries = await create_category(db_session, budget, group, "Groceries")
    household = await create_category(db_session, budget, group, "Household")
    payee = await create_payee(db_session, budget, "Target")

    flat = await create_transaction(
        db_session, budget, checking, "-163.94", TODAY - timedelta(days=1),
        payee=payee, cleared="uncleared",
    )
    parent, children = await _make_split(
        db_session, budget, checking, TODAY, "-163.94",
        [("-100.00", groceries), ("-63.94", household)], payee=payee,
    )
    activity_before = await services.transaction_repo.sum_by_category_by_month(
        groceries.id, TODAY
    )

    created = await services.matching.scan_for_duplicates(checking.id)
    assert created == 1
    matches = await services.match_repo.get_pending_for_account(checking.id)
    assert len(matches) == 1
    assert matches[0].synced_transaction_id == parent.id, "newer row is cast as synced"

    await services.matching.accept_match(matches[0].id)

    assert not (await _row(db_session, parent.id)).is_deleted, "the split parent survives"
    assert (await _row(db_session, flat.id)).is_deleted, "the flat duplicate is merged away"
    for child in children:
        assert not (await _row(db_session, child.id)).is_deleted
    activity_after = await services.transaction_repo.sum_by_category_by_month(
        groceries.id, TODAY
    )
    assert activity_after == activity_before, "category activity must not move on a merge"
    await assert_financial_invariants(db_session, budget.id)


async def test_scan_accept_keeps_transfer_leg_partner_untouched(db_session):
    services, budget, checking = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")
    out_leg, in_leg = await _make_transfer(db_session, budget, checking, savings, "200.00", TODAY)
    flat = await create_transaction(
        db_session, budget, checking, "-200.00", TODAY, cleared="uncleared"
    )

    created = await services.matching.scan_for_duplicates(checking.id)
    assert created == 1
    matches = await services.match_repo.get_pending_for_account(checking.id)
    await services.matching.accept_match(matches[0].id)

    assert not (await _row(db_session, out_leg.id)).is_deleted, "the transfer leg survives"
    assert (await _row(db_session, flat.id)).is_deleted
    partner = await _row(db_session, in_leg.id)
    assert not partner.is_deleted
    assert partner.amount == Decimal("200.00")
    assert partner.transfer_id == out_leg.id, "the partner link is untouched"
    await assert_financial_invariants(db_session, budget.id)


async def test_reconciled_flat_vs_split_parent_blocks_and_stays_pending(db_session):
    """Reconciled outranks structure for the keeper role — which would make
    the split parent the loser. That merge is unresolvable: it must raise,
    mutate nothing, and leave the match pending."""
    services, budget, checking = await _setup(db_session)
    group = await create_category_group(db_session, budget)
    groceries = await create_category(db_session, budget, group, "Groceries")

    synced_flat = await create_transaction(
        db_session, budget, checking, "-88.00", TODAY,
        cleared="reconciled", sync_id="t-guard-1", sync_source="simplefin",
    )
    parent, children = await _make_split(
        db_session, budget, checking, TODAY, "-88.00",
        [("-50.00", groceries), ("-38.00", None)],
    )
    match = await services.match_repo.create(
        synced_transaction_id=synced_flat.id,
        manual_transaction_id=parent.id,
        confidence_score=0.8,
    )

    with pytest.raises(InvariantViolation, match="split"):
        await services.matching.accept_match(match.id)

    refreshed = await services.match_repo.get(match.id)
    assert refreshed.status == "pending", "a blocked accept leaves the match for the user"
    assert not (await _row(db_session, synced_flat.id)).is_deleted
    assert not (await _row(db_session, parent.id)).is_deleted
    for child in children:
        assert not (await _row(db_session, child.id)).is_deleted
    await assert_financial_invariants(db_session, budget.id)


async def test_reconciled_split_parent_wins_and_absorbs_identity(db_session):
    services, budget, checking = await _setup(db_session)
    parent, children = await _make_split(
        db_session, budget, checking, TODAY, "-120.00",
        [("-70.00", None), ("-50.00", None)], cleared="reconciled",
    )
    synced_flat = await create_transaction(
        db_session, budget, checking, "-120.00", TODAY,
        cleared="cleared", sync_id="t-guard-2", sync_source="simplefin",
    )
    match = await services.match_repo.create(
        synced_transaction_id=synced_flat.id,
        manual_transaction_id=parent.id,
        confidence_score=0.8,
    )

    await services.matching.accept_match(match.id)

    keeper = await _row(db_session, parent.id)
    assert not keeper.is_deleted
    assert keeper.sync_id == "t-guard-2", "bank identity lands on the reconciled split parent"
    assert keeper.sync_source == "simplefin"
    assert keeper.bank_posted_date == TODAY
    assert keeper.cleared == "reconciled", "reconciled state is never downgraded"
    for child in children:
        assert (await _row(db_session, child.id)).cleared == "reconciled"
    assert (await _row(db_session, synced_flat.id)).is_deleted
    await assert_financial_invariants(db_session, budget.id)


async def test_transfer_leg_absorbs_sync_id_under_unique_index(db_session):
    """The loser holds (account_id, sync_id) under the partial unique index;
    delete-first ordering is what lets the keeper take that identity without
    tripping the index."""
    services, budget, checking = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")
    out_leg, in_leg = await _make_transfer(db_session, budget, checking, savings, "150.00", TODAY)
    synced_flat = await create_transaction(
        db_session, budget, checking, "-150.00", TODAY,
        cleared="cleared", sync_id="t-leg-dup", sync_source="simplefin",
    )
    match = await services.match_repo.create(
        synced_transaction_id=synced_flat.id,
        manual_transaction_id=out_leg.id,
        confidence_score=0.8,
    )

    await services.matching.accept_match(match.id)

    keeper = await _row(db_session, out_leg.id)
    assert keeper.sync_id == "t-leg-dup"
    assert keeper.sync_source == "simplefin"
    assert keeper.has_sync_source is True
    assert keeper.bank_posted_date == TODAY
    assert (await _row(db_session, synced_flat.id)).is_deleted
    assert not (await _row(db_session, in_leg.id)).is_deleted
    await assert_financial_invariants(db_session, budget.id)


async def test_scan_skips_both_structured_pairs(db_session):
    """Two structured rows can never merge — the scan must not offer them."""
    services, budget, checking = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")
    await _make_split(
        db_session, budget, checking, TODAY, "-163.94",
        [("-100.00", None), ("-63.94", None)],
    )
    await _make_split(
        db_session, budget, checking, TODAY, "-163.94",
        [("-90.00", None), ("-73.94", None)],
    )
    out_leg, _ = await _make_transfer(db_session, budget, checking, savings, "163.94", TODAY)
    assert out_leg.amount == Decimal("-163.94"), "leg pairs with the parents on amount"

    created = await services.matching.scan_for_duplicates(checking.id)

    assert created == 0, "split-parent/split-parent and split-parent/leg pairs are unresolvable"
    assert await services.match_repo.get_pending_for_account(checking.id) == []
    await assert_financial_invariants(db_session, budget.id)


async def test_idless_bank_row_confers_identity_on_accept(db_session):
    """An id-less feed row (sync_source set, sync_id NULL) is still the bank's
    row: merging it away must move sync_source, posted-date provenance, and
    the cleared upgrade onto the keeper."""
    services, budget, checking = await _setup(db_session)
    payee = await create_payee(db_session, budget, "Corner Market")
    manual = await create_transaction(
        db_session, budget, checking, "-42.00", TODAY - timedelta(days=1),
        payee=payee, cleared="uncleared",
    )
    idless = await create_transaction(
        db_session, budget, checking, "-42.00", TODAY,
        payee=payee, cleared="cleared", sync_source="simplefin",
    )

    created = await services.matching.scan_for_duplicates(checking.id)
    assert created == 1
    matches = await services.match_repo.get_pending_for_account(checking.id)
    assert matches[0].synced_transaction_id == idless.id

    await services.matching.accept_match(matches[0].id)

    keeper = await _row(db_session, manual.id)
    assert not keeper.is_deleted
    assert keeper.sync_id is None
    assert keeper.sync_source == "simplefin", "id-less bank identity transfers"
    assert keeper.has_sync_source is True
    assert keeper.bank_posted_date == TODAY, "the bank row's date arrives as provenance"
    assert keeper.cleared == "cleared", "the bank's sighting upgrades cleared"
    assert (await _row(db_session, idless.id)).is_deleted
    await assert_financial_invariants(db_session, budget.id)


async def test_accept_clears_split_children_then_reconciles_clean(db_session):
    """A cleared upgrade on a split parent must reach the children; the
    reconcile that follows would otherwise strand uncleared children under a
    reconciled parent."""
    services, budget, checking = await _setup(db_session)
    parent, children = await _make_split(
        db_session, budget, checking, TODAY, "-163.94",
        [("-100.00", None), ("-63.94", None)], cleared="uncleared",
    )
    synced_flat = await create_transaction(
        db_session, budget, checking, "-163.94", TODAY,
        cleared="cleared", sync_id="t-guard-f4", sync_source="simplefin",
    )
    match = await services.match_repo.create(
        synced_transaction_id=synced_flat.id,
        manual_transaction_id=parent.id,
        confidence_score=0.8,
    )

    await services.matching.accept_match(match.id)

    keeper = await _row(db_session, parent.id)
    assert keeper.sync_id == "t-guard-f4"
    assert keeper.cleared == "cleared"
    for child in children:
        assert (await _row(db_session, child.id)).cleared == "cleared", (
            "children mirror the parent's cleared upgrade"
        )
    await assert_financial_invariants(db_session, budget.id)

    await services.reconciliation.finish(checking.id, Decimal("-163.94"))

    assert (await _row(db_session, parent.id)).cleared == "reconciled"
    for child in children:
        assert (await _row(db_session, child.id)).cleared == "reconciled"
    await assert_financial_invariants(db_session, budget.id)


async def test_try_match_auto_accept_keeps_split_parent(db_session):
    """The sync-time auto-accept path: a fresh bank row matching a split
    parent's total merges into the parent, never the other way around."""
    services, budget, checking = await _setup(db_session)
    payee = await create_payee(db_session, budget, "Target")
    parent, children = await _make_split(
        db_session, budget, checking, TODAY, "-163.94",
        [("-100.00", None), ("-63.94", None)], payee=payee,
    )
    synced_flat = await create_transaction(
        db_session, budget, checking, "-163.94", TODAY,
        payee=payee, cleared="cleared", sync_id="t-guard-9", sync_source="simplefin",
    )

    await services.matching.try_match(synced_flat)

    keeper = await _row(db_session, parent.id)
    assert not keeper.is_deleted, "the split parent survives the auto-accept"
    assert keeper.sync_id == "t-guard-9"
    assert (await _row(db_session, synced_flat.id)).is_deleted
    for child in children:
        assert not (await _row(db_session, child.id)).is_deleted
    await assert_financial_invariants(db_session, budget.id)
