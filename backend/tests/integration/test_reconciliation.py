"""Phase 3 spec: reconciliation always locks an account that agrees with the
statement, and reconciled is a controlled state (finish grants it, only the
explicit unreconcile removes it).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from igab.db.models import Account, ReconciliationSnapshot, Transaction, TransactionMatch
from igab.domain.exceptions import InvariantViolation
from igab.services.reconciliation_service import ReconciliationBlocked
from igab.services.transaction_service import TransactionCreate, TransactionUpdate
from igab.utils.clock import today_utc

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
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
    adjustment = await services.transaction_repo.get_or_raise(snapshot.adjustment_transaction_id)
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

    # Reconciliation locks the money, not the bookkeeping.
    with pytest.raises(InvariantViolation, match="unlock it to change amount"):
        await services.transactions.update(
            budget.id, parent.id, TransactionUpdate(amount=Decimal("-81.00"))
        )
    await services.transactions.update(
        budget.id, parent.id, TransactionUpdate(memo="filed after the statement")
    )
    await db_session.refresh(parent)
    assert parent.memo == "filed after the statement"
    assert parent.cleared == "reconciled", "a bookkeeping edit does not unlock the row"


async def test_a_reconciled_transfer_leg_can_be_relinked(db_session):
    """Retargeting the far leg moves the partner; this row's money never moves."""
    services, budget, checking = await _setup(db_session)
    savings = await create_account(db_session, budget, "Savings")
    brokerage = await create_account(db_session, budget, "Brokerage")
    leg = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=checking.id,
            date=TODAY,
            amount=Decimal("-50.00"),
            cleared="cleared",
            transfer_account_id=savings.id,
        ),
    )
    await services.reconciliation.finish(checking.id, Decimal("-50.00"))
    await db_session.refresh(leg)
    assert leg.cleared == "reconciled"

    updated = await services.transactions.update(
        budget.id, leg.id, TransactionUpdate(transfer_account_id=brokerage.id)
    )
    assert updated.cleared == "reconciled"
    assert updated.amount == Decimal("-50.00") and updated.date == TODAY
    partner = await services.transaction_repo.get(updated.transfer_id)
    assert partner is not None and partner.account_id == brokerage.id


async def _reconciled_row_via_api(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group, "Groceries")
    txn = await create_transaction(db_session, budget, account, "-10.00", TODAY, cleared="cleared")
    await make_services(db_session).reconciliation.finish(account.id, Decimal("-10.00"))
    await db_session.refresh(txn)
    assert txn.cleared == "reconciled"
    return budget, category, txn


async def test_bulk_categorize_reaches_reconciled_rows(api_client, db_session):
    budget, category, txn = await _reconciled_row_via_api(api_client, db_session)
    resp = await api_client.patch(
        f"/api/v1/{budget.id}/transactions/bulk-categorize",
        json={"transaction_ids": [str(txn.id)], "category_id": str(category.id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated"] == [str(txn.id)] and body["failed"] == []
    await db_session.refresh(txn)
    assert txn.category_id == category.id and txn.cleared == "reconciled"


async def test_bulk_cleared_reports_reconciled_rows_as_failed(api_client, db_session):
    budget, _category, txn = await _reconciled_row_via_api(api_client, db_session)
    resp = await api_client.patch(
        f"/api/v1/{budget.id}/transactions/bulk-cleared",
        json={"transaction_ids": [str(txn.id)], "cleared": "uncleared"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated"] == []
    assert [f["id"] for f in body["failed"]] == [str(txn.id)]
    assert "reconciled" in body["failed"][0]["reason"]
    await db_session.refresh(txn)
    assert txn.cleared == "reconciled"


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
    txn = await create_transaction(db_session, budget, checking, "-45.00", TODAY, cleared="cleared")
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
    txn = await create_transaction(db_session, budget, checking, "-45.00", TODAY, cleared="cleared")

    with pytest.raises(InvariantViolation, match="not reconciled"):
        await services.transactions.unreconcile(budget.id, txn.id)


async def test_user_cannot_set_reconciled_or_pending_via_update(db_session):
    services, budget, checking = await _setup(db_session)
    txn = await create_transaction(
        db_session, budget, checking, "-45.00", TODAY, cleared="uncleared"
    )

    for value in ("reconciled", "pending"):
        with pytest.raises(InvariantViolation):
            await services.transactions.update(budget.id, txn.id, TransactionUpdate(cleared=value))


async def test_future_dated_cleared_txn_excluded_from_status(db_session):
    """A future-dated cleared transaction cannot be on any bank statement, so
    it must not move the cleared balance or manufacture an adjustment."""
    services, budget, checking = await _setup(db_session)
    await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")
    await create_transaction(
        db_session,
        budget,
        checking,
        "-120.00",
        today_utc() + timedelta(days=5),
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
    await create_transaction(db_session, budget, checking, "250.00", today_utc(), cleared="cleared")

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
        db_session,
        budget,
        checking,
        "-75.00",
        today_utc() + timedelta(days=10),
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
        db_session,
        budget,
        checking,
        "-999.00",
        today_utc() + timedelta(days=1),
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


async def test_adjustment_is_recorded_in_the_change_log(db_session):
    """An adjustment moves real money, so it belongs in the change log like
    any other transaction — otherwise the user can't see or undo it."""
    from sqlalchemy import select

    from igab.db.models import ChangeLog

    services, budget, checking = await _setup(db_session)
    await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")

    adjustment = await services.reconciliation.create_adjustment(checking.id, Decimal("-1.00"))

    await db_session.flush()
    result = await db_session.execute(
        select(ChangeLog).where(
            ChangeLog.budget_id == budget.id,
            ChangeLog.entity_type == "transaction",
            ChangeLog.entity_id == adjustment.id,
        )
    )
    change = result.scalars().one()
    assert change.action == "create"
    assert Decimal(change.after["amount"]) == Decimal("-1.00")


async def test_adjustment_never_inherits_a_category_from_an_earlier_one(db_session):
    """Adjustments stay uncategorized so the difference lands in Ready to
    Assign. Auto-categorization would quietly file the second one under
    whatever category the user gave the first."""
    services, budget, checking = await _setup(db_session)
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")

    first = await services.reconciliation.create_adjustment(checking.id, Decimal("-1.00"))
    await services.transactions.update(
        budget.id, first.id, TransactionUpdate(category_id=groceries.id)
    )

    second = await services.reconciliation.create_adjustment(checking.id, Decimal("-2.00"))

    assert second.category_id is None
    assert second.payee_id == first.payee_id, "same adjustment payee, no inherited category"


class TestTheHeaderAndReconcileDifferOnlyOnFutureRows:
    """Two numbers are labelled "cleared balance", and they are allowed to
    differ — but by exactly one thing.

    The header reports a partition: balance = cleared + uncleared. Reconcile
    asks what today's statement should say. Applying reconcile's date cutoff
    to the header would not remove a future-dated cleared row from it; it
    would move that row into *uncleared*, which is a worse answer. So the
    divergence is intended, and these tests bound it — see `not_future` in
    txn_filters.py.
    """

    async def test_they_agree_when_nothing_is_future_dated(self, db_session):
        services, budget, checking = await _setup(db_session)
        await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")
        await create_transaction(
            db_session, budget, checking, "-120.00", TODAY, cleared="reconciled"
        )
        await create_transaction(db_session, budget, checking, "-30.00", TODAY, cleared="uncleared")

        header = await services.account_repo.get_cleared_balance(checking.id)
        status = await services.reconciliation.get_status(checking.id)

        assert header == Decimal("380.00")
        assert Decimal(str(status["cleared_balance"])) == header

    async def test_they_differ_by_exactly_the_future_dated_cleared_rows(self, db_session):
        services, budget, checking = await _setup(db_session)
        await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")
        future = today_utc() + timedelta(days=10)
        await create_transaction(db_session, budget, checking, "250.00", future, cleared="cleared")

        header = await services.account_repo.get_cleared_balance(checking.id)
        status = await services.reconciliation.get_status(checking.id)

        assert header == Decimal("750.00")
        assert Decimal(str(status["cleared_balance"])) == Decimal("500.00")
        assert header - Decimal(str(status["cleared_balance"])) == Decimal("250.00")

    async def test_a_future_dated_cleared_row_is_never_reported_as_uncleared(self, db_session):
        # The failure mode of "just add the cutoff to get_cleared_balance":
        # uncleared_balance is derived as balance - cleared, so cutting only
        # the cleared term relabels the row rather than excluding it.
        services, budget, checking = await _setup(db_session)
        await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")
        future = today_utc() + timedelta(days=10)
        await create_transaction(db_session, budget, checking, "250.00", future, cleared="cleared")

        balance = await services.account_repo.get_balance(checking.id)
        cleared = await services.account_repo.get_cleared_balance(checking.id)

        assert balance == Decimal("750.00")
        assert balance - cleared == Decimal("0.00")

    async def test_the_header_partition_holds_with_a_pending_row_present(self, db_session):
        # Pending is excluded from balance entirely, so it belongs to neither
        # term. The partition is over posted rows only.
        services, budget, checking = await _setup(db_session)
        await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")
        await create_transaction(db_session, budget, checking, "-40.00", TODAY, cleared="uncleared")
        await create_transaction(db_session, budget, checking, "-999.00", TODAY, cleared="pending")

        balance = await services.account_repo.get_balance(checking.id)
        cleared = await services.account_repo.get_cleared_balance(checking.id)

        assert balance == Decimal("460.00")
        assert cleared == Decimal("500.00")
        assert balance - cleared == Decimal("-40.00")

    async def test_the_adjustment_is_sized_against_the_statement_question(self, db_session):
        # The consequence that matters: even while the header shows a larger
        # number, finish() must not manufacture an adjustment for a statement
        # that already agrees.
        services, budget, checking = await _setup(db_session)
        await create_transaction(db_session, budget, checking, "500.00", TODAY, cleared="cleared")
        future = today_utc() + timedelta(days=10)
        await create_transaction(db_session, budget, checking, "250.00", future, cleared="cleared")

        snapshot = await services.reconciliation.finish(checking.id, Decimal("500.00"))

        assert snapshot.adjustment_transaction_id is None
        await assert_financial_invariants(db_session, budget.id)


class TestReconcileWaitsForTheDuplicateReview:
    """A reconciliation is refused while a duplicate review holds cleared rows.

    The incident, rescaled: a sync queued the bank's $64.20 copy of a
    pharmacy purchase beside the person's own cleared row. The cleared
    balance counted it twice, so reconciling to the bank's $935.80 wrote an
    adjustment of -$64.20. Accepting the merge then removed the double,
    leaving the ledger $64.20 short of the bank on an account now reconciled
    — a drift fault nothing could explain, with advice to refetch 90 days.

    The slice is txn_filters.IN_REVIEW_CLEARED, the same rows drift reports
    as `in_review`; `get_status` counts it and `finish` and the adjustment
    refuse until it is zero. Figures are invented.
    """

    #: The bank's figure: a $1,000.00 paycheck less one $64.20 purchase.
    BANK = Decimal("935.80")
    #: What the cleared balance reads while the purchase is counted twice.
    DOUBLED = Decimal("871.60")

    async def _account_with_paycheck(self, db_session, budget) -> Account:
        account = await create_account(db_session, budget, "Harborstone Checking")
        await create_transaction(db_session, budget, account, "1000.00", TODAY, cleared="cleared")
        return account

    async def _pair(
        self,
        db_session,
        budget,
        account,
        *,
        on: date = TODAY,
        own_cleared: str = "cleared",
        bank_copy_deleted: bool = False,
        sync_id: str = "rx-1",
    ) -> TransactionMatch:
        """The person's -64.20 and the bank's queued copy of it."""
        own = await create_transaction(
            db_session, budget, account, "-64.20", on, cleared=own_cleared
        )
        bank_copy = await create_transaction(
            db_session,
            budget,
            account,
            "-64.20",
            TODAY,
            cleared="cleared",
            sync_id=sync_id,
            bank_posted_date=TODAY,
            is_deleted=bank_copy_deleted,
        )
        match = TransactionMatch(
            synced_transaction_id=bank_copy.id,
            manual_transaction_id=own.id,
            confidence_score=Decimal("0.60"),
            status="pending",
        )
        db_session.add(match)
        await db_session.flush()
        return match

    async def _row_count(self, db_session, account) -> int:
        return (
            await db_session.execute(
                select(func.count(Transaction.id)).where(Transaction.account_id == account.id)
            )
        ).scalar_one()

    async def test_an_open_pair_blocks_finish_and_writes_nothing(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        account = await self._account_with_paycheck(db_session, budget)
        await self._pair(db_session, budget, account)

        status = (await api_client.get(f"/api/v1/accounts/{account.id}/reconcile/status")).json()
        assert status["in_review_count"] == 1
        # The doubled figure the old finish reconciled against.
        assert Decimal(str(status["cleared_balance"])) == self.DOUBLED

        r = await api_client.post(
            f"/api/v1/accounts/{account.id}/reconcile/finish",
            json={"statement_balance": str(self.BANK)},
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == (
            "1 possible duplicate on this account is waiting in review — settle it "
            "first, or the reconciliation will count it twice."
        )

        assert await self._row_count(db_session, account) == 3, "no adjustment was written"
        cleared_states = (
            await db_session.execute(
                select(Transaction.cleared).where(Transaction.account_id == account.id)
            )
        ).scalars()
        assert set(cleared_states) == {"cleared"}, "nothing was locked"
        snapshots = await db_session.execute(
            select(ReconciliationSnapshot.id).where(ReconciliationSnapshot.account_id == account.id)
        )
        assert snapshots.first() is None
        await db_session.refresh(account)
        assert account.last_reconciled_at is None

    async def test_an_open_pair_blocks_the_adjustment_too(self, db_session, api_client):
        """The bar's Create adjustment is the same mistake one step earlier:
        the difference it would cover is the doubled money itself."""
        budget = await create_budget(db_session, api_client.test_user)
        account = await self._account_with_paycheck(db_session, budget)
        await self._pair(db_session, budget, account)

        r = await api_client.post(
            f"/api/v1/accounts/{account.id}/reconcile/adjustment",
            json={"adjustment_amount": "64.20"},
        )
        assert r.status_code == 409, r.text
        assert await self._row_count(db_session, account) == 3

    async def test_accepting_the_merge_unblocks_and_leaves_no_drift(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        account = await self._account_with_paycheck(db_session, budget)
        account.simplefin_balance = self.BANK
        match = await self._pair(db_session, budget, account)

        r = await api_client.post(f"/api/v1/simplefin/matches/{match.id}/accept")
        assert r.status_code in (200, 204), r.text

        status = (await api_client.get(f"/api/v1/accounts/{account.id}/reconcile/status")).json()
        assert status["in_review_count"] == 0
        assert Decimal(str(status["cleared_balance"])) == self.BANK

        r = await api_client.post(
            f"/api/v1/accounts/{account.id}/reconcile/finish",
            json={"statement_balance": str(self.BANK)},
        )
        assert r.status_code == 200, r.text
        assert Decimal(str(r.json()["adjustment_amount"])) == Decimal("0")

        served = (await api_client.get(f"/api/v1/accounts/{account.id}")).json()
        assert served["last_reconciled_at"] is not None
        assert Decimal(str(served["bank_drift"])) == Decimal("0")
        assert served["bank_drift_is_fault"] is False
        await assert_financial_invariants(db_session, budget.id)

    async def test_rejecting_the_pair_also_settles_it(self, db_session):
        """Rejecting keeps both rows as two real purchases — counted twice on
        purpose now, so there is nothing left to wait for."""
        services, budget, _checking = await _setup(db_session)
        account = await self._account_with_paycheck(db_session, budget)
        match = await self._pair(db_session, budget, account)

        await services.matching.reject_match(match.id)

        status = await services.reconciliation.get_status(account.id)
        assert status["in_review_count"] == 0
        snapshot = await services.reconciliation.finish(account.id, self.DOUBLED)
        assert snapshot.adjustment_transaction_id is None

    async def test_the_message_counts_every_open_pair(self, db_session):
        services, budget, _checking = await _setup(db_session)
        account = await self._account_with_paycheck(db_session, budget)
        await self._pair(db_session, budget, account, sync_id="rx-1")
        await self._pair(db_session, budget, account, sync_id="rx-2")

        assert (await services.reconciliation.get_status(account.id))["in_review_count"] == 2
        with pytest.raises(
            ReconciliationBlocked,
            match=(
                "^2 possible duplicates on this account are waiting in review — settle "
                "them first, or the reconciliation will count them twice.$"
            ),
        ):
            await services.reconciliation.finish(account.id, self.BANK)
        with pytest.raises(ReconciliationBlocked):
            await services.reconciliation.create_adjustment(account.id, Decimal("128.40"))

    async def test_an_uncleared_own_row_does_not_block(self, db_session):
        """Last week's hand-typed entry, not yet cleared: only the bank's copy
        is in the cleared balance, so the purchase is counted once already."""
        services, budget, _checking = await _setup(db_session)
        account = await self._account_with_paycheck(db_session, budget)
        await self._pair(db_session, budget, account, own_cleared="uncleared")

        status = await services.reconciliation.get_status(account.id)
        assert status["in_review_count"] == 0
        assert status["cleared_balance"] == self.BANK
        snapshot = await services.reconciliation.finish(account.id, self.BANK)
        assert snapshot.adjustment_transaction_id is None

    async def test_a_pair_whose_bank_copy_was_deleted_does_not_block(self, db_session):
        """A deleted bank copy duplicates nothing — the pair is stale."""
        services, budget, _checking = await _setup(db_session)
        account = await self._account_with_paycheck(db_session, budget)
        await self._pair(db_session, budget, account, bank_copy_deleted=True)

        status = await services.reconciliation.get_status(account.id)
        assert status["in_review_count"] == 0
        assert status["cleared_balance"] == self.BANK
        snapshot = await services.reconciliation.finish(account.id, self.BANK)
        assert snapshot.adjustment_transaction_id is None

    async def test_a_future_dated_own_row_does_not_block(self, db_session):
        """A statement cannot include a row dated after today, and the cleared
        balance reconcile reads already leaves it out — see `not_future` — so
        it doubles nothing the statement is compared with."""
        services, budget, _checking = await _setup(db_session)
        account = await self._account_with_paycheck(db_session, budget)
        await self._pair(db_session, budget, account, on=today_utc() + timedelta(days=5))

        status = await services.reconciliation.get_status(account.id)
        assert status["in_review_count"] == 0
        assert status["cleared_balance"] == self.BANK
        snapshot = await services.reconciliation.finish(account.id, self.BANK)
        assert snapshot.adjustment_transaction_id is None
