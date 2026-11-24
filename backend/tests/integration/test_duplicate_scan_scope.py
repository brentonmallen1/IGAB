"""What the duplicate scan looks through, and the way out of its queue.

The scan compared every row in the account with every other: any age,
reconciled or not, and pairs the merge itself would refuse. On a budget with
years of history that queued dozens of "possible duplicates" that were two
real charges — a weekly coffee, a twice-monthly transfer — each of which could
only be answered one at a time, and each of which held the account's
reconciliation back until it was.

Fixtures are invented: a checking account and round, repeated amounts.
"""

from datetime import date, timedelta
from decimal import Decimal

from igab.db.models import Transaction, TransactionMatch
from igab.services.undo_service import UndoService

from .factories import (
    create_account,
    create_budget,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date(2026, 7, 10)


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    payee = await create_payee(db_session, budget, "Corner Cafe")
    return services, budget, checking, payee


async def _pair(db_session, budget, account, payee, day, *, cleared=("uncleared", "uncleared")):
    """Two same-amount rows a day apart — what a duplicate looks like."""
    a = await create_transaction(
        db_session, budget, account, "-12.00", day, payee=payee, cleared=cleared[0]
    )
    b = await create_transaction(
        db_session,
        budget,
        account,
        "-12.00",
        day + timedelta(days=1),
        payee=payee,
        cleared=cleared[1],
    )
    return a, b


class TestScope:
    async def test_by_default_reconciled_rows_are_left_alone(self, db_session):
        services, budget, checking, payee = await _setup(db_session)
        await _pair(db_session, budget, checking, payee, TODAY, cleared=("reconciled", "cleared"))
        await _pair(db_session, budget, checking, payee, TODAY - timedelta(days=30))

        assert await services.matching.scan_for_duplicates(checking.id) == 1
        (match,) = await services.match_repo.get_pending_for_account(checking.id)
        for row_id in (match.synced_transaction_id, match.manual_transaction_id):
            assert (await db_session.get(Transaction, row_id)).cleared != "reconciled"

    async def test_including_reconciled_pairs_one_with_a_row_that_is_not(self, db_session):
        services, budget, checking, payee = await _setup(db_session)
        await _pair(db_session, budget, checking, payee, TODAY, cleared=("reconciled", "cleared"))

        assert await services.matching.scan_for_duplicates(checking.id) == 0
        assert (
            await services.matching.scan_for_duplicates(checking.id, include_reconciled=True) == 1
        )

    async def test_two_reconciled_rows_are_never_paired(self, db_session):
        """The statement vouched for both, so the merge refuses — and a pair
        nobody can accept is not a question worth asking."""
        services, budget, checking, payee = await _setup(db_session)
        await _pair(
            db_session, budget, checking, payee, TODAY, cleared=("reconciled", "reconciled")
        )
        assert (
            await services.matching.scan_for_duplicates(checking.id, include_reconciled=True) == 0
        )

    async def test_since_leaves_older_rows_out(self, db_session):
        services, budget, checking, payee = await _setup(db_session)
        await _pair(db_session, budget, checking, payee, TODAY - timedelta(days=400))
        recent_a, recent_b = await _pair(db_session, budget, checking, payee, TODAY)

        created = await services.matching.scan_for_duplicates(
            checking.id, since=TODAY - timedelta(days=90)
        )
        assert created == 1
        (match,) = await services.match_repo.get_pending_for_account(checking.id)
        assert {match.synced_transaction_id, match.manual_transaction_id} == {
            recent_a.id,
            recent_b.id,
        }

    async def test_since_needs_both_rows_inside_the_window(self, db_session):
        services, budget, checking, payee = await _setup(db_session)
        edge = TODAY - timedelta(days=90)
        await _pair(db_session, budget, checking, payee, edge - timedelta(days=1))
        assert await services.matching.scan_for_duplicates(checking.id, since=edge) == 0

    async def test_no_scope_still_scans_everything_unreconciled(self, db_session):
        services, budget, checking, payee = await _setup(db_session)
        await _pair(db_session, budget, checking, payee, TODAY - timedelta(days=400))
        await _pair(db_session, budget, checking, payee, TODAY)
        assert await services.matching.scan_for_duplicates(checking.id) == 2


class TestOnlyWhatCouldMerge:
    async def test_two_bank_records_with_different_ids_are_two_charges(self, db_session):
        """The bank reported them separately. The merge has always refused
        this pair; the scan queued it anyway."""
        services, budget, checking, payee = await _setup(db_session)
        await create_transaction(
            db_session, budget, checking, "-12.00", TODAY, payee=payee, sync_id="TRN-1"
        )
        await create_transaction(
            db_session,
            budget,
            checking,
            "-12.00",
            TODAY + timedelta(days=1),
            payee=payee,
            sync_id="TRN-2",
        )
        assert await services.matching.scan_for_duplicates(checking.id) == 0

    async def test_a_bank_record_and_a_hand_entered_row_still_pair(self, db_session):
        services, budget, checking, payee = await _setup(db_session)
        await create_transaction(
            db_session, budget, checking, "-12.00", TODAY, payee=payee, sync_id="TRN-1"
        )
        await create_transaction(
            db_session, budget, checking, "-12.00", TODAY, payee=payee, cleared="uncleared"
        )
        assert await services.matching.scan_for_duplicates(checking.id) == 1


class TestKeepAllSeparate:
    async def test_rejects_every_open_pair_and_they_are_not_proposed_again(self, db_session):
        services, budget, checking, payee = await _setup(db_session)
        await _pair(db_session, budget, checking, payee, TODAY)
        await _pair(db_session, budget, checking, payee, TODAY - timedelta(days=30))
        assert await services.matching.scan_for_duplicates(checking.id) == 2

        rejected, batch_id = await services.matching.reject_all_pending(checking.id)
        assert rejected == 2 and batch_id is not None
        assert await services.match_repo.get_pending_for_account(checking.id) == []
        # Remembered: the next scan does not ask the same question again.
        assert await services.matching.scan_for_duplicates(checking.id) == 0

    async def test_touches_only_this_account(self, db_session):
        services, budget, checking, payee = await _setup(db_session)
        savings = await create_account(db_session, budget, "Savings")
        await _pair(db_session, budget, checking, payee, TODAY)
        await _pair(db_session, budget, savings, payee, TODAY)
        await services.matching.scan_for_duplicates(checking.id)
        await services.matching.scan_for_duplicates(savings.id)

        await services.matching.reject_all_pending(checking.id)
        assert len(await services.match_repo.get_pending_for_account(savings.id)) == 1

    async def test_nothing_open_is_nothing_done(self, db_session):
        services, budget, checking, payee = await _setup(db_session)
        assert await services.matching.reject_all_pending(checking.id) == (0, None)

    async def test_one_undo_reopens_them_all(self, db_session):
        services, budget, checking, payee = await _setup(db_session)
        await _pair(db_session, budget, checking, payee, TODAY)
        await _pair(db_session, budget, checking, payee, TODAY - timedelta(days=30))
        await services.matching.scan_for_duplicates(checking.id)
        _, batch_id = await services.matching.reject_all_pending(checking.id)
        await db_session.flush()

        await UndoService(db_session).undo_batch(budget.id, batch_id)
        assert len(await services.match_repo.get_pending_for_account(checking.id)) == 2


class TestEndpoints:
    async def test_scan_takes_its_scope_from_the_body(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        payee = await create_payee(db_session, budget, "Corner Cafe")
        today = date.today()
        await _pair(db_session, budget, checking, payee, today - timedelta(days=400))
        await _pair(db_session, budget, checking, payee, today - timedelta(days=3))
        await db_session.commit()

        r = await api_client.post(
            f"/api/v1/accounts/{checking.id}/scan-duplicates",
            json={"since": str(today - timedelta(days=90))},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"created": 1}
        # No body at all still works, and reaches the older pair.
        r = await api_client.post(f"/api/v1/accounts/{checking.id}/scan-duplicates")
        assert r.json() == {"created": 1}

    async def test_reject_all_answers_with_a_batch_the_undo_takes(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        payee = await create_payee(db_session, budget, "Corner Cafe")
        a, b = await _pair(db_session, budget, checking, payee, date.today())
        db_session.add(
            TransactionMatch(
                synced_transaction_id=b.id,
                manual_transaction_id=a.id,
                confidence_score=Decimal("0.8"),
                status="pending",
            )
        )
        await db_session.commit()

        r = await api_client.post(f"/api/v1/accounts/{checking.id}/pending-matches/reject-all")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rejected"] == 1 and body["batch_id"]
        pending = await api_client.get(f"/api/v1/accounts/{checking.id}/pending-matches")
        assert pending.json() == []

        r = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{body['batch_id']}/undo")
        assert r.status_code == 200, r.text
        pending = await api_client.get(f"/api/v1/accounts/{checking.id}/pending-matches")
        assert len(pending.json()) == 1
