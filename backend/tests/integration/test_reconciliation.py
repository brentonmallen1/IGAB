"""Phase 3 spec: reconciliation always locks an account that agrees with the
statement, and reconciled is a controlled state (finish grants it, only the
explicit unreconcile removes it).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.services.transaction_service import TransactionCreate, TransactionUpdate
from igab.utils.clock import today_utc

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


async def test_finish_exact_balance_no_adjustment(db_session):
    services, budget, checking = await _setup(db_session)
    await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")

    snapshot = await services.reconciliation.finish(checking.id, Decimal("500.00"))

    assert snapshot.adjustment_amount == Decimal("0")
    assert snapshot.adjustment_transaction_id is None
    status = await services.reconciliation.get_status(checking.id)
    assert status["cleared_balance"] == Decimal("500.00")


async def test_finish_creates_adjustment_when_statement_differs(db_session):
    """A $1 mismatch produces an automatic adjustment so the locked account
    always equals the statement."""
    services, budget, checking = await _setup(db_session)
    await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")

    snapshot = await services.reconciliation.finish(checking.id, Decimal("499.00"))

    assert snapshot.adjustment_amount == Decimal("-1.00")
    assert snapshot.adjustment_transaction_id is not None
    adjustment = await services.transaction_repo.get_or_raise(
        snapshot.adjustment_transaction_id
    )
    assert adjustment.amount == Decimal("-1.00")
    assert adjustment.cleared == "reconciled", "adjustment locks with the rest"
    assert await services.account_repo.get_balance(checking.id) == Decimal("499.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_finish_locks_cleared_parents_and_children(db_session):
    services, budget, checking = await _setup(db_session)
    header = TransactionCreate(
        account_id=checking.id, date=TODAY, amount=Decimal("-80.00"), cleared="cleared"
    )
    splits = [
        TransactionCreate(account_id=checking.id, date=TODAY, amount=Decimal("-80.00")),
    ]
    parent = await services.transactions.create_split(budget.id, header, splits)

    await services.reconciliation.finish(checking.id, Decimal("-80.00"))

    await db_session.refresh(parent)
    assert parent.cleared == "reconciled"
    for child in await services.transaction_repo.get_splits(parent.id):
        assert child.cleared == "reconciled", "children lock with the parent"

    with pytest.raises(InvariantViolation):
        await services.transactions.update(
            budget.id, parent.id, TransactionUpdate(memo="nope")
        )


async def test_race_transaction_between_status_and_finish_absorbed(db_session):
    """Simulates the UI reading status, then a sync adding a cleared txn,
    then finish: the recompute inside finish() creates the adjustment."""
    services, budget, checking = await _setup(db_session)
    await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")

    ui_status = await services.reconciliation.get_status(checking.id)
    assert ui_status["cleared_balance"] == Decimal("500.00")

    # A sync lands another cleared transaction before the user hits finish
    await create_transaction(db_session, budget, checking, "-30.00", TODAY, cleared="cleared")

    snapshot = await services.reconciliation.finish(checking.id, Decimal("500.00"))

    # Statement said 500; actual cleared was 470 → +30 adjustment
    assert snapshot.adjustment_amount == Decimal("30.00")
    assert await services.account_repo.get_balance(checking.id) == Decimal("500.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_unreconcile_unlocks_transaction(db_session):
    services, budget, checking = await _setup(db_session)
    txn = await create_transaction(
        db_session, budget, checking, "-45.00", TODAY, cleared="cleared"
    )
    await services.reconciliation.finish(checking.id, Decimal("-45.00"))
    await db_session.refresh(txn)
    assert txn.cleared == "reconciled"

    await services.transactions.unreconcile(budget.id, txn.id)
    await db_session.refresh(txn)
    assert txn.cleared == "cleared"

    # Now editable again
    await services.transactions.update(budget.id, txn.id, TransactionUpdate(memo="fixed"))
    await db_session.refresh(txn)
    assert txn.memo == "fixed"


async def test_unreconcile_requires_reconciled(db_session):
    services, budget, checking = await _setup(db_session)
    txn = await create_transaction(
        db_session, budget, checking, "-45.00", TODAY, cleared="cleared"
    )

    with pytest.raises(InvariantViolation, match="not reconciled"):
        await services.transactions.unreconcile(budget.id, txn.id)


async def test_user_cannot_set_reconciled_or_pending_via_update(db_session):
    services, budget, checking = await _setup(db_session)
    txn = await create_transaction(
        db_session, budget, checking, "-45.00", TODAY, cleared="uncleared"
    )

    for value in ("reconciled", "pending"):
        with pytest.raises(InvariantViolation):
            await services.transactions.update(
                budget.id, txn.id, TransactionUpdate(cleared=value)
            )


async def test_future_dated_cleared_txn_excluded_from_status(db_session):
    """A future-dated cleared transaction cannot be on any bank statement, so
    it must not move the cleared balance or manufacture an adjustment."""
    services, budget, checking = await _setup(db_session)
    await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")
    await create_transaction(
        db_session, budget, checking, "-120.00", today_utc() + timedelta(days=5),
        cleared="cleared",
    )

    status = await services.reconciliation.get_status(checking.id)
    assert status["cleared_balance"] == Decimal("500.00")


async def test_future_dated_uncleared_and_pending_excluded_from_counts(db_session):
    """Counts guide the user during reconciliation; future-dated rows aren't
    reconcilable yet so they shouldn't nag."""
    services, budget, checking = await _setup(db_session)
    future = today_utc() + timedelta(days=3)
    await create_transaction(db_session, budget, checking, "-10.00", TODAY, cleared="uncleared")
    await create_transaction(db_session, budget, checking, "-20.00", future, cleared="uncleared")
    await create_transaction(db_session, budget, checking, "-30.00", future, cleared="pending")

    status = await services.reconciliation.get_status(checking.id)
    assert status["uncleared_count"] == 1
    assert status["pending_count"] == 0


async def test_txn_dated_today_included_in_status(db_session):
    """Boundary: today's transactions are on the statement side of the cutoff."""
    services, budget, checking = await _setup(db_session)
    await create_transaction(
        db_session, budget, checking, "250.00", today_utc(), cleared="cleared"
    )

    status = await services.reconciliation.get_status(checking.id)
    assert status["cleared_balance"] == Decimal("250.00")


async def test_finish_ignores_future_cleared_txn_and_leaves_it_unlocked(db_session):
    """finish() with a future-dated cleared txn present: no adjustment when the
    statement matches past activity, and the future txn stays 'cleared' —
    locking it as reconciled would bless an amount the statement never saw."""
    services, budget, checking = await _setup(db_session)
    past = await create_transaction(
        db_session, budget, checking, "500.00", TODAY, cleared="cleared"
    )
    future = await create_transaction(
        db_session, budget, checking, "-75.00", today_utc() + timedelta(days=10),
        cleared="cleared",
    )

    snapshot = await services.reconciliation.finish(checking.id, Decimal("500.00"))

    assert snapshot.adjustment_amount == Decimal("0")
    assert snapshot.adjustment_transaction_id is None
    await db_session.refresh(past)
    await db_session.refresh(future)
    assert past.cleared == "reconciled"
    assert future.cleared == "cleared", "future txn must not be locked"
    await assert_financial_invariants(db_session, budget.id)


async def test_finish_adjustment_based_on_past_activity_only(db_session):
    """Statement disagrees with past cleared activity while a future cleared
    txn exists: the adjustment must reflect only the past."""
    services, budget, checking = await _setup(db_session)
    await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")
    await create_transaction(
        db_session, budget, checking, "-999.00", today_utc() + timedelta(days=1),
        cleared="cleared",
    )

    snapshot = await services.reconciliation.finish(checking.id, Decimal("480.00"))

    # 480 statement - 500 past cleared = -20; the future -999 plays no part
    assert snapshot.adjustment_amount == Decimal("-20.00")
    await assert_financial_invariants(db_session, budget.id)


async def test_api_rejects_reconciled_cleared_on_create_and_bulk(api_client, db_session):
    from .factories import create_account, create_budget

    user = api_client.test_user
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")

    resp = await api_client.post(
        f"/api/v1/{budget.id}/transactions",
        json={
            "account_id": str(account.id),
            "date": "2026-07-10",
            "amount": "-10.00",
            "cleared": "reconciled",
        },
    )
    assert resp.status_code == 422, "reconciled is not a user-settable status"

    resp = await api_client.patch(
        f"/api/v1/{budget.id}/transactions/bulk-cleared",
        json={"transaction_ids": [], "cleared": "pending"},
    )
    assert resp.status_code == 422, "pending is reserved for bank sync"
