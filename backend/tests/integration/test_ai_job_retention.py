"""AI activity retention + the transaction-removed badge flag.

Retention deletes only finished (done/error) log rows past the cutoff —
active jobs and transactions/attachments are never touched. The badge flag
marks jobs whose linked transaction was deleted after the fact.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from igab.db.models import AIJob
from igab.repositories.settings_repo import SettingsRepository
from igab.services.settings_service import SettingsService
from igab.tasks.ai_worker import run_retention_cleanup

from .factories import create_account, create_budget, create_transaction

NOW = datetime.now(UTC)


async def _setup(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    return budget, account


async def make_job(
    db_session,
    budget,
    *,
    status: str = "done",
    finished_at: datetime | None = None,
    transaction_id: uuid.UUID | None = None,
) -> AIJob:
    job = AIJob(
        budget_id=budget.id,
        kind="receipt",
        status=status,
        payload={},
        finished_at=finished_at,
        transaction_id=transaction_id,
    )
    db_session.add(job)
    await db_session.flush()
    return job


class TestTransactionRemovedFlag:
    async def test_flag_reflects_transaction_deletion(self, api_client, db_session):
        budget, account = await _setup(api_client, db_session)
        txn = await create_transaction(db_session, budget, account, "-12.34", NOW.date())
        job = await make_job(db_session, budget, transaction_id=txn.id, finished_at=NOW)

        listing = (await api_client.get(f"/api/v1/{budget.id}/ai/jobs")).json()
        assert listing["jobs"][0]["transaction_removed"] is False

        txn.is_deleted = True
        await db_session.flush()

        listing = (await api_client.get(f"/api/v1/{budget.id}/ai/jobs")).json()
        assert listing["jobs"][0]["transaction_removed"] is True

        detail = (await api_client.get(f"/api/v1/{budget.id}/ai/jobs/{job.id}")).json()
        assert detail["transaction_removed"] is True

    async def test_job_without_transaction_is_not_flagged(self, api_client, db_session):
        budget, _ = await _setup(api_client, db_session)
        await make_job(db_session, budget, finished_at=NOW)

        listing = (await api_client.get(f"/api/v1/{budget.id}/ai/jobs")).json()
        assert listing["jobs"][0]["transaction_removed"] is False


class TestRetentionCleanup:
    async def test_deletes_only_old_finished_jobs(self, api_client, db_session):
        budget, _ = await _setup(api_client, db_session)
        old = NOW - timedelta(days=40)
        old_done = await make_job(db_session, budget, status="done", finished_at=old)
        old_error = await make_job(db_session, budget, status="error", finished_at=old)
        recent_done = await make_job(db_session, budget, status="done", finished_at=NOW)
        still_queued = await make_job(db_session, budget, status="queued")

        deleted = await run_retention_cleanup(db_session)

        assert set(deleted) == {old_done.id, old_error.id}
        assert await db_session.get(AIJob, recent_done.id) is not None
        assert await db_session.get(AIJob, still_queued.id) is not None
        assert await db_session.get(AIJob, old_done.id) is None

    async def test_zero_retention_keeps_everything(self, api_client, db_session):
        budget, _ = await _setup(api_client, db_session)
        await SettingsService(SettingsRepository(db_session)).set(
            "ai_activity_retention_days", "0"
        )
        old_done = await make_job(
            db_session, budget, status="done", finished_at=NOW - timedelta(days=400)
        )

        deleted = await run_retention_cleanup(db_session)

        assert deleted == []
        assert await db_session.get(AIJob, old_done.id) is not None

    async def test_custom_retention_window(self, api_client, db_session):
        budget, _ = await _setup(api_client, db_session)
        await SettingsService(SettingsRepository(db_session)).set(
            "ai_activity_retention_days", "7"
        )
        too_old = await make_job(
            db_session, budget, status="done", finished_at=NOW - timedelta(days=10)
        )
        recent = await make_job(
            db_session, budget, status="error", finished_at=NOW - timedelta(days=3)
        )

        deleted = await run_retention_cleanup(db_session)

        assert set(deleted) == {too_old.id}
        assert await db_session.get(AIJob, recent.id) is not None

    async def test_cleanup_never_touches_transactions(self, api_client, db_session):
        budget, account = await _setup(api_client, db_session)
        txn = await create_transaction(db_session, budget, account, "-5.00", NOW.date())
        await make_job(
            db_session,
            budget,
            status="done",
            finished_at=NOW - timedelta(days=40),
            transaction_id=txn.id,
        )

        await run_retention_cleanup(db_session)

        await db_session.refresh(txn)
        assert txn.is_deleted is False
        assert txn.amount == Decimal("-5.00")
