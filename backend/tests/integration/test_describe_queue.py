"""A description is queued like a receipt — nobody waits on the model.

Describe used to parse inline: the phone sat on a spinner until Ollama
answered, then filled the form. On a local model that is long enough to give
up at a checkout. Now the words are handed off, and the worker files the
row for review exactly as it does a scan: in the account it was given,
waiting unplaced in AI Activity with none, on the bank's row once that
arrives, and as a $0 stub when the model cannot read it — never lost.
"""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from igab.db.models import AIJob, Payee, Transaction, TransactionAttachment
from igab.domain.receipt_fields import DESCRIPTION_FAILURE_MEMO
from igab.services.ai_service import AIService
from igab.services.settings_service import SettingsService
from igab.tasks.ai_worker import NonRetryableJobError, process_one_job, record_job_failure

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
)

WORDS = "coffee at the corner bakery 6.50 yesterday"
READ = {
    "payee": "Corner Bakery",
    "amount": 6.50,
    "direction": "outflow",
    "date": "2026-09-20",
    "category": "Dining Out",
    "memo": None,
    "confidence": 0.9,
}


@pytest.fixture
def model(monkeypatch):
    mock = AsyncMock(return_value=dict(READ))
    monkeypatch.setattr(AIService, "parse_nl_transaction", mock)
    return mock


async def _budget(db_session, user):
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    dining = await create_category(db_session, budget, group, "Dining Out")
    await db_session.flush()
    return budget, checking, dining


async def _job(db_session, budget, account=None, text=WORDS) -> AIJob:
    payload = {"text": text, "client_today": "2026-09-21"}
    if account is not None:
        payload["account_id"] = str(account.id)
    job = AIJob(
        budget_id=budget.id, kind="nl_parse", status="processing", attempts=1, payload=payload
    )
    db_session.add(job)
    await db_session.flush()
    return job


async def _txn_count(db_session, budget) -> int:
    return await db_session.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.budget_id == budget.id)
    )


class TestSubmitting:
    async def test_it_is_queued_and_answers_at_once(self, api_client, db_session, model):
        budget, checking, _ = await _budget(db_session, api_client.test_user)
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/{budget.id}/ai/descriptions",
            json={
                "text": f"  {WORDS} ",
                "account_id": str(checking.id),
                "client_today": "2026-09-21",
            },
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert (body["kind"], body["status"]) == ("nl_parse", "queued")
        assert body["payload"]["text"] == WORDS
        # Handed off, not read: the model is the worker's to call.
        model.assert_not_called()

    async def test_the_account_is_optional(self, api_client, db_session):
        budget, *_ = await _budget(db_session, api_client.test_user)
        await db_session.commit()
        r = await api_client.post(f"/api/v1/{budget.id}/ai/descriptions", json={"text": WORDS})
        assert r.status_code == 202, r.text
        assert "account_id" not in r.json()["payload"]

    async def test_blank_words_are_refused(self, api_client, db_session):
        budget, *_ = await _budget(db_session, api_client.test_user)
        await db_session.commit()
        r = await api_client.post(f"/api/v1/{budget.id}/ai/descriptions", json={"text": "   "})
        assert r.status_code == 422

    async def test_another_budgets_account_is_refused(self, api_client, db_session):
        budget, *_ = await _budget(db_session, api_client.test_user)
        other = await create_user(db_session, email="other@example.com")
        foreign = await create_account(db_session, await create_budget(db_session, other), "Theirs")
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/{budget.id}/ai/descriptions",
            json={"text": WORDS, "account_id": str(foreign.id)},
        )
        assert r.status_code == 404

    async def test_no_model_host_is_the_one_refusal(self, api_client, db_session, monkeypatch):
        async def blank_host(self, key, default=None):
            return "" if key == "ollama_host" else default

        monkeypatch.setattr(SettingsService, "get", blank_host)
        budget, *_ = await _budget(db_session, api_client.test_user)
        await db_session.commit()
        r = await api_client.post(f"/api/v1/{budget.id}/ai/descriptions", json={"text": WORDS})
        assert r.status_code == 503


class TestTheWorker:
    async def test_with_an_account_it_files_an_unapproved_row(self, db_session, model, api_client):
        budget, checking, dining = await _budget(db_session, api_client.test_user)
        job = await _job(db_session, budget, checking)
        await process_one_job(db_session, job)

        assert job.status == "done"
        txn = await db_session.get(Transaction, job.transaction_id)
        assert (txn.account_id, txn.amount, txn.date) == (
            checking.id,
            Decimal("-6.50"),
            date(2026, 9, 20),
        )
        assert (txn.category_id, txn.approved, txn.created_via) == (dining.id, False, "ai_nl")
        payee = await db_session.get(Payee, txn.payee_id)
        assert payee is not None and payee.name == "Corner Bakery"
        # Words, not a photo: nothing to attach.
        assert job.attachment_id is None
        model.assert_awaited_once_with(budget.id, WORDS, date(2026, 9, 21))

    async def test_with_no_account_it_waits_and_moves_nothing(self, db_session, model, api_client):
        budget, *_ = await _budget(db_session, api_client.test_user)
        before = await _txn_count(db_session, budget)
        job = await _job(db_session, budget)
        await process_one_job(db_session, job)
        assert (job.status, job.transaction_id) == ("unplaced", None)
        assert await _txn_count(db_session, budget) == before
        assert job.result["draft"]["amount"] == "-6.50"

    async def test_empty_words_fail_without_a_retry(self, db_session, model, api_client):
        budget, checking, _ = await _budget(db_session, api_client.test_user)
        job = await _job(db_session, budget, checking, text="  ")
        with pytest.raises(NonRetryableJobError):
            await process_one_job(db_session, job)
        model.assert_not_called()

    async def test_an_unreadable_description_becomes_a_stub_to_finish(self, db_session, api_client):
        # Like a failed scan: a $0 row to finish by hand, the words on its job.
        budget, checking, _ = await _budget(db_session, api_client.test_user)
        job = await _job(db_session, budget, checking)
        await record_job_failure(db_session, job, NonRetryableJobError("unreadable"))
        assert job.status == "error"
        txn = await db_session.get(Transaction, job.transaction_id)
        assert (txn.amount, txn.memo, txn.created_via, txn.approved) == (
            Decimal("0"),
            DESCRIPTION_FAILURE_MEMO,
            "ai_nl",
            False,
        )

    async def test_an_unreadable_one_with_no_account_waits(self, db_session, api_client):
        budget, *_ = await _budget(db_session, api_client.test_user)
        job = await _job(db_session, budget)
        await record_job_failure(db_session, job, NonRetryableJobError("unreadable"))
        assert (job.status, job.transaction_id) == ("unplaced", None)

    async def test_reprocessing_refreshes_its_own_row(self, db_session, model, api_client):
        # The row is the description's own (`ai_nl`), so a fresh read may move
        # its amount — the rule a scan's own row follows.
        budget, checking, _ = await _budget(db_session, api_client.test_user)
        job = await _job(db_session, budget, checking)
        await process_one_job(db_session, job)
        first = job.transaction_id
        model.return_value = {**READ, "amount": 7.25}
        await process_one_job(db_session, job)
        assert job.transaction_id == first
        txn = await db_session.get(Transaction, first)
        await db_session.refresh(txn)
        assert txn.amount == Decimal("-7.25")

    async def test_a_stub_is_read_over_on_reprocess(self, db_session, model, api_client):
        budget, checking, dining = await _budget(db_session, api_client.test_user)
        job = await _job(db_session, budget, checking)
        await record_job_failure(db_session, job, NonRetryableJobError("unreadable"))
        await process_one_job(db_session, job)
        txn = await db_session.get(Transaction, job.transaction_id)
        await db_session.refresh(txn)
        # The stub's memo is the app's, not the person's: the read clears it.
        assert (txn.amount, txn.category_id, txn.memo) == (Decimal("-6.50"), dining.id, None)


class TestPlacingOne:
    async def _unplaced(self, db_session, budget):
        job = await _job(db_session, budget)
        await process_one_job(db_session, job)
        await db_session.commit()
        return job

    async def test_it_needs_the_user_and_the_badge_counts_it(self, api_client, db_session, model):
        budget, *_ = await _budget(db_session, api_client.test_user)
        job = await self._unplaced(db_session, budget)
        r = await api_client.get(f"/api/v1/{budget.id}/ai/jobs", params={"needs_review": True})
        assert [j["id"] for j in r.json()["jobs"]] == [str(job.id)]
        r = await api_client.get(f"/api/v1/{budget.id}/ai/jobs/active-count")
        assert r.json()["needs_review"] == 1

    async def test_in_an_account(self, api_client, db_session, model):
        budget, checking, dining = await _budget(db_session, api_client.test_user)
        job = await self._unplaced(db_session, budget)
        r = await api_client.post(
            f"/api/v1/{budget.id}/ai/jobs/{job.id}/place", json={"account_id": str(checking.id)}
        )
        # No image to have lost — placing a receipt refuses without one.
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["status"], body["transaction_account_id"]) == ("done", str(checking.id))
        assert body["attachment_id"] is None
        txn = await db_session.get(Transaction, uuid.UUID(body["transaction_id"]))
        await db_session.refresh(txn)
        assert (txn.amount, txn.category_id, txn.created_via) == (
            Decimal("-6.50"),
            dining.id,
            "ai_nl",
        )

    async def test_on_the_banks_row_once_it_arrives(self, api_client, db_session, model):
        budget, checking, dining = await _budget(db_session, api_client.test_user)
        job = await self._unplaced(db_session, budget)
        row = await create_transaction(db_session, budget, checking, "-6.50", date(2026, 9, 21))
        await db_session.commit()
        match = (await api_client.get(f"/api/v1/{budget.id}/ai/jobs/{job.id}")).json()["bank_match"]
        assert match["id"] == str(row.id)

        before = await _txn_count(db_session, budget)
        r = await api_client.post(
            f"/api/v1/{budget.id}/ai/jobs/{job.id}/place", json={"transaction_id": str(row.id)}
        )
        assert r.status_code == 200, r.text
        assert await _txn_count(db_session, budget) == before
        await db_session.refresh(row)
        # The bank's date and amount stand; what it was missing is filled.
        assert (row.amount, row.date, row.category_id) == (
            Decimal("-6.50"),
            date(2026, 9, 21),
            dining.id,
        )
        attachments = await db_session.scalar(
            select(func.count())
            .select_from(TransactionAttachment)
            .where(TransactionAttachment.transaction_id == row.id)
        )
        assert attachments == 0

    async def test_an_unreadable_one_is_placed_as_the_stub(self, api_client, db_session):
        budget, checking, _ = await _budget(db_session, api_client.test_user)
        job = await _job(db_session, budget)
        await record_job_failure(db_session, job, NonRetryableJobError("unreadable"))
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/{budget.id}/ai/jobs/{job.id}/place", json={"account_id": str(checking.id)}
        )
        assert r.status_code == 200, r.text
        txn = await db_session.get(Transaction, uuid.UUID(r.json()["transaction_id"]))
        assert (txn.amount, txn.memo) == (Decimal("0"), DESCRIPTION_FAILURE_MEMO)
