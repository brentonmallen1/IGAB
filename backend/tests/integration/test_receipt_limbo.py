"""A receipt scanned with no account waits — and moves no money while it does.

It becomes a transaction only once something says where it belongs: the card
printed on it (an ending on file for an open account), the bank's own row
for it, or a person choosing. Until then it is an `unplaced` job with its
image kept, filed with the rows that need the user, and counted on the badge.
"""

import uuid
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy import func, select

import igab.config
from igab.db.models import AccountCardEnding, AIJob, Transaction, TransactionAttachment
from igab.repositories.ai_job_repo import AIJobRepository
from igab.services.ai_service import AIService
from igab.tasks.ai_worker import NonRetryableJobError, process_one_job, record_job_failure

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
)

EXTRACTION = {
    "payee": "Hardware Store",
    "total": 24.00,
    "date": "2026-09-20",
    "category": "Garden",
    "confidence": 0.9,
    "memo": "Trowel and gloves",
    "suggested_split": [],
    "card_last4": "4417",
}


def tiny_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def attachments_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(igab.config.settings, "ATTACHMENTS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def extraction(monkeypatch):
    monkeypatch.setattr(
        AIService, "check_vision_support", AsyncMock(return_value=(None, "gemma4", False))
    )
    monkeypatch.setattr(AIService, "is_receipt_image", AsyncMock(return_value=True))
    mock = AsyncMock(return_value=dict(EXTRACTION))
    monkeypatch.setattr(AIService, "extract_receipt", mock)
    return mock


async def _budget(db_session, user):
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    group = await create_category_group(db_session, budget, "Home")
    garden = await create_category(db_session, budget, group, "Garden")
    await db_session.flush()
    return budget, checking, card, garden


async def _remember(db_session, budget, account, last4="4417"):
    db_session.add(AccountCardEnding(budget_id=budget.id, account_id=account.id, last4=last4))
    await db_session.flush()


async def _job(db_session, attachments_dir, budget, account=None) -> AIJob:
    job_id = uuid.uuid4()
    stage = attachments_dir / "ai_staging" / str(job_id)
    stage.mkdir(parents=True)
    (stage / "receipt.jpg").write_bytes(tiny_jpeg())
    payload = {
        "original_filename": "receipt.jpg",
        "content_type": "image/jpeg",
        "staged_path": f"ai_staging/{job_id}/receipt.jpg",
        "client_today": "2026-09-21",
    }
    if account is not None:
        payload["account_id"] = str(account.id)
    job = AIJob(
        id=job_id,
        budget_id=budget.id,
        kind="receipt",
        status="processing",
        attempts=1,
        payload=payload,
    )
    db_session.add(job)
    await db_session.flush()
    return job


async def _txn_count(db_session, budget) -> int:
    return await db_session.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.budget_id == budget.id)
    )


def _staged(attachments_dir, job) -> bool:
    return (attachments_dir / "ai_staging" / str(job.id) / "receipt.jpg").exists()


class TestTheWorker:
    async def test_no_account_and_no_known_card_waits_and_moves_nothing(
        self, db_session, attachments_dir, extraction, api_client
    ):
        budget, *_ = await _budget(db_session, api_client.test_user)
        before = await _txn_count(db_session, budget)
        job = await _job(db_session, attachments_dir, budget)
        await process_one_job(db_session, job)
        assert job.status == "unplaced"
        assert job.transaction_id is None
        assert await _txn_count(db_session, budget) == before
        assert job.result["draft"]["amount"] == "-24.00"
        assert _staged(attachments_dir, job)  # kept until it is placed

    async def test_a_known_card_places_it_unapproved_in_that_account(
        self, db_session, attachments_dir, extraction, api_client
    ):
        budget, _, card, garden = await _budget(db_session, api_client.test_user)
        await _remember(db_session, budget, card)
        job = await _job(db_session, attachments_dir, budget)
        await process_one_job(db_session, job)
        assert job.status == "done"
        txn = await db_session.get(Transaction, job.transaction_id)
        assert (txn.account_id, txn.approved, txn.category_id) == (card.id, False, garden.id)
        assert job.result["placed_by"] == "card_ending"
        assert not _staged(attachments_dir, job)

    async def test_the_banks_row_takes_the_receipt_instead_of_a_duplicate(
        self, db_session, attachments_dir, extraction, api_client
    ):
        budget, _, card, garden = await _budget(db_session, api_client.test_user)
        await _remember(db_session, budget, card)
        bank_row = await create_transaction(db_session, budget, card, "-24.00", date(2026, 9, 21))
        before = await _txn_count(db_session, budget)
        job = await _job(db_session, attachments_dir, budget)
        await process_one_job(db_session, job)
        assert job.transaction_id == bank_row.id
        assert await _txn_count(db_session, budget) == before
        await db_session.refresh(bank_row)
        # Only what the row was missing comes from the receipt.
        assert (bank_row.category_id, bank_row.memo) == (garden.id, "Trowel and gloves")
        attachment = await db_session.get(TransactionAttachment, job.attachment_id)
        assert attachment.transaction_id == bank_row.id

    async def test_a_card_on_a_closed_account_places_nothing(
        self, db_session, attachments_dir, extraction, api_client
    ):
        budget, _, card, _ = await _budget(db_session, api_client.test_user)
        await _remember(db_session, budget, card)
        card.is_closed = True
        await db_session.flush()
        job = await _job(db_session, attachments_dir, budget)
        await process_one_job(db_session, job)
        assert job.status == "unplaced"

    async def test_a_chosen_account_still_wins_over_the_card(
        self, db_session, attachments_dir, extraction, api_client
    ):
        # The card warns in review; it never overrides what a person chose.
        budget, checking, card, _ = await _budget(db_session, api_client.test_user)
        await _remember(db_session, budget, card)
        job = await _job(db_session, attachments_dir, budget, checking)
        await process_one_job(db_session, job)
        txn = await db_session.get(Transaction, job.transaction_id)
        assert txn.account_id == checking.id
        assert "placed_by" not in job.result

    async def test_a_failed_scan_with_no_account_waits_with_its_image(
        self, db_session, attachments_dir, api_client
    ):
        budget, *_ = await _budget(db_session, api_client.test_user)
        job = await _job(db_session, attachments_dir, budget)
        await record_job_failure(db_session, job, NonRetryableJobError("not a receipt"))
        assert (job.status, job.transaction_id) == ("unplaced", None)
        assert _staged(attachments_dir, job)

    async def test_retention_keeps_waiting_receipts(
        self, db_session, attachments_dir, extraction, api_client
    ):
        from datetime import UTC, datetime, timedelta

        budget, *_ = await _budget(db_session, api_client.test_user)
        job = await _job(db_session, attachments_dir, budget)
        await process_one_job(db_session, job)
        deleted = await AIJobRepository(db_session).delete_finished_before(
            datetime.now(UTC) + timedelta(days=1)
        )
        assert job.id not in deleted


class TestTheApi:
    async def _unplaced(self, db_session, attachments_dir, budget):
        job = await _job(db_session, attachments_dir, budget)
        await process_one_job(db_session, job)
        await db_session.commit()
        assert job.status == "unplaced"
        return job

    async def test_a_receipt_can_be_submitted_with_no_account(
        self, api_client, db_session, attachments_dir
    ):
        budget, *_ = await _budget(db_session, api_client.test_user)
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/{budget.id}/ai/receipts",
            files={"file": ("receipt.jpg", tiny_jpeg(), "image/jpeg")},
            data={"client_today": "2026-09-21"},
        )
        assert r.status_code == 202, r.text
        assert "account_id" not in r.json()["payload"]

    async def test_it_needs_the_user_and_the_badge_counts_it(
        self, api_client, db_session, attachments_dir, extraction
    ):
        budget, *_ = await _budget(db_session, api_client.test_user)
        job = await self._unplaced(db_session, attachments_dir, budget)
        r = await api_client.get(f"/api/v1/{budget.id}/ai/jobs", params={"needs_review": True})
        assert [j["id"] for j in r.json()["jobs"]] == [str(job.id)]
        r = await api_client.get(f"/api/v1/{budget.id}/ai/jobs/active-count")
        assert r.json()["needs_review"] == 1

    async def test_the_banks_row_is_offered_once_it_arrives(
        self, api_client, db_session, attachments_dir, extraction
    ):
        budget, _, card, _ = await _budget(db_session, api_client.test_user)
        job = await self._unplaced(db_session, attachments_dir, budget)
        r = await api_client.get(f"/api/v1/{budget.id}/ai/jobs/{job.id}")
        assert r.json()["bank_match"] is None
        row = await create_transaction(db_session, budget, card, "-24.00", date(2026, 9, 22))
        await db_session.commit()
        match = (await api_client.get(f"/api/v1/{budget.id}/ai/jobs/{job.id}")).json()["bank_match"]
        assert (match["id"], match["account_id"], Decimal(str(match["amount"]))) == (
            str(row.id),
            str(card.id),
            Decimal("-24.00"),
        )

    async def test_two_candidate_rows_offer_neither(
        self, api_client, db_session, attachments_dir, extraction
    ):
        budget, checking, card, _ = await _budget(db_session, api_client.test_user)
        job = await self._unplaced(db_session, attachments_dir, budget)
        await create_transaction(db_session, budget, card, "-24.00", date(2026, 9, 22))
        await create_transaction(db_session, budget, checking, "-24.00", date(2026, 9, 19))
        await db_session.commit()
        r = await api_client.get(f"/api/v1/{budget.id}/ai/jobs/{job.id}")
        assert r.json()["bank_match"] is None

    async def test_placing_in_an_account_uses_todays_categories(
        self, api_client, db_session, attachments_dir, extraction
    ):
        budget, checking, _, _ = await _budget(db_session, api_client.test_user)
        extraction.return_value = {**EXTRACTION, "category": "Tools"}
        job = await self._unplaced(db_session, attachments_dir, budget)
        # "Tools" did not exist when it was read; it does when it is placed.
        group = await create_category_group(db_session, budget, "Workshop")
        tools = await create_category(db_session, budget, group, "Tools")
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/{budget.id}/ai/jobs/{job.id}/place", json={"account_id": str(checking.id)}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["status"], body["transaction_account_id"]) == ("done", str(checking.id))
        # Placing is a mutating endpoint: it serves the category it just filed.
        assert (body["transaction_category_id"], body["transaction_is_split"]) == (
            str(tools.id),
            False,
        )
        txn = await db_session.get(Transaction, uuid.UUID(body["transaction_id"]))
        await db_session.refresh(txn)
        assert (txn.amount, txn.category_id, txn.approved) == (Decimal("-24.00"), tools.id, False)
        assert body["attachment_id"] is not None

    async def test_placing_on_the_banks_row(
        self, api_client, db_session, attachments_dir, extraction
    ):
        budget, _, card, _ = await _budget(db_session, api_client.test_user)
        job = await self._unplaced(db_session, attachments_dir, budget)
        row = await create_transaction(db_session, budget, card, "-24.00", date(2026, 9, 22))
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/{budget.id}/ai/jobs/{job.id}/place", json={"transaction_id": str(row.id)}
        )
        assert r.status_code == 200, r.text
        assert r.json()["transaction_id"] == str(row.id)

    async def test_a_failed_scan_is_placed_as_the_usual_stub(
        self, api_client, db_session, attachments_dir
    ):
        budget, checking, _, _ = await _budget(db_session, api_client.test_user)
        job = await _job(db_session, attachments_dir, budget)
        await record_job_failure(db_session, job, NonRetryableJobError("not a receipt"))
        await db_session.commit()
        r = await api_client.post(
            f"/api/v1/{budget.id}/ai/jobs/{job.id}/place", json={"account_id": str(checking.id)}
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "error"  # still says why it needs finishing by hand
        txn = await db_session.get(Transaction, uuid.UUID(r.json()["transaction_id"]))
        assert txn.amount == 0

    async def test_the_place_request_is_one_thing(
        self, api_client, db_session, attachments_dir, extraction
    ):
        budget, checking, _, _ = await _budget(db_session, api_client.test_user)
        job = await self._unplaced(db_session, attachments_dir, budget)
        url = f"/api/v1/{budget.id}/ai/jobs/{job.id}/place"
        assert (await api_client.post(url, json={})).status_code == 422
        both = {"account_id": str(checking.id), "transaction_id": str(uuid.uuid4())}
        assert (await api_client.post(url, json=both)).status_code == 422
        ok = await api_client.post(url, json={"account_id": str(checking.id)})
        assert ok.status_code == 200
        again = await api_client.post(url, json={"account_id": str(checking.id)})
        assert again.status_code == 409

    async def test_a_placed_receipt_undoes_away_from_activity(
        self, api_client, db_session, attachments_dir, extraction
    ):
        # Recorded like every AI-made row: source "ai", so a bare ⌘Z skips it
        # (latest_live_manual) and the Activity page undoes it by id.
        budget, checking, _, _ = await _budget(db_session, api_client.test_user)
        job = await self._unplaced(db_session, attachments_dir, budget)
        before = await _txn_count(db_session, budget)
        placed = await api_client.post(
            f"/api/v1/{budget.id}/ai/jobs/{job.id}/place", json={"account_id": str(checking.id)}
        )
        txn_id = placed.json()["transaction_id"]
        changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
        [create] = [c for c in changes if c["entity_id"] == txn_id and c["action"] == "create"]
        assert create["source"] == "ai"
        r = await api_client.post(f"/api/v1/{budget.id}/changes/{create['id']}/undo")
        assert r.status_code == 200, r.text
        live = await db_session.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.budget_id == budget.id, Transaction.is_deleted == False)  # noqa: E712
        )
        assert live == before
