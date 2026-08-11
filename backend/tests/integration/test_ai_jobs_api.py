"""AI jobs API: submit/list/detail/retry/delete, ownership scoping, the
ai_job_id link on transaction create, and the has_attachment filter."""

import uuid
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select

import igab.config
from igab.db.models import AIJob, Transaction

from .factories import create_account, create_budget, create_transaction, create_user


def tiny_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def attachments_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(igab.config.settings, "ATTACHMENTS_DIR", str(tmp_path))
    return tmp_path


async def _setup(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    return budget, account


async def _submit(api_client, budget, account, **extra):
    return await api_client.post(
        f"/api/v1/{budget.id}/ai/receipts",
        files={"file": ("receipt.jpg", tiny_jpeg(), "image/jpeg")},
        data={"account_id": str(account.id), "client_today": "2026-08-02", **extra},
    )


class TestSubmitReceipt:
    async def test_submit_queues_job_and_stages_file(
        self, api_client, db_session, attachments_dir
    ):
        budget, account = await _setup(api_client, db_session)
        resp = await _submit(api_client, budget, account)
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        assert body["kind"] == "receipt"
        # staged_path is internal — never exposed
        assert "staged_path" not in body["payload"]

        job = await db_session.get(AIJob, uuid.UUID(body["id"]))
        assert job is not None
        staged = attachments_dir / job.payload["staged_path"]
        assert staged.exists()
        assert staged.read_bytes() == tiny_jpeg()

    async def test_foreign_budget_404(self, api_client, db_session, attachments_dir):
        other = await create_user(db_session, email="other@example.com")
        foreign_budget = await create_budget(db_session, other)
        foreign_account = await create_account(db_session, foreign_budget, "Their Checking")
        resp = await _submit(api_client, foreign_budget, foreign_account)
        assert resp.status_code == 404

    async def test_foreign_account_404(self, api_client, db_session, attachments_dir):
        budget, _ = await _setup(api_client, db_session)
        other = await create_user(db_session, email="other2@example.com")
        foreign_budget = await create_budget(db_session, other)
        foreign_account = await create_account(db_session, foreign_budget, "Their Checking")
        resp = await _submit(api_client, budget, foreign_account)
        assert resp.status_code == 404

    async def test_bad_content_type_rejected(self, api_client, db_session, attachments_dir):
        budget, account = await _setup(api_client, db_session)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/ai/receipts",
            files={"file": ("notes.txt", b"lunch was $12", "text/plain")},
            data={"account_id": str(account.id)},
        )
        assert resp.status_code == 400

    async def test_bad_client_today_rejected(self, api_client, db_session, attachments_dir):
        budget, account = await _setup(api_client, db_session)
        resp = await _submit(api_client, budget, account, client_today="last tuesday")
        assert resp.status_code == 422


class TestJobListingAndLifecycle:
    async def test_list_detail_active_count(self, api_client, db_session, attachments_dir):
        budget, account = await _setup(api_client, db_session)
        submitted = (await _submit(api_client, budget, account)).json()

        listing = (await api_client.get(f"/api/v1/{budget.id}/ai/jobs")).json()
        assert listing["total_count"] == 1
        assert listing["jobs"][0]["id"] == submitted["id"]

        detail = await api_client.get(f"/api/v1/{budget.id}/ai/jobs/{submitted['id']}")
        assert detail.status_code == 200

        count = (await api_client.get(f"/api/v1/{budget.id}/ai/jobs/active-count")).json()
        assert count["count"] == 1

    async def test_jobs_scoped_to_budget(self, api_client, db_session, attachments_dir):
        budget, account = await _setup(api_client, db_session)
        job_id = (await _submit(api_client, budget, account)).json()["id"]

        other = await create_user(db_session, email="other3@example.com")
        foreign_budget = await create_budget(db_session, other)
        for method, url in [
            ("get", f"/api/v1/{foreign_budget.id}/ai/jobs"),
            ("get", f"/api/v1/{foreign_budget.id}/ai/jobs/{job_id}"),
            ("post", f"/api/v1/{foreign_budget.id}/ai/jobs/{job_id}/retry"),
            ("delete", f"/api/v1/{foreign_budget.id}/ai/jobs/{job_id}"),
        ]:
            resp = await getattr(api_client, method)(url)
            assert resp.status_code == 404, f"{method} {url} -> {resp.status_code}"

    async def test_retry_only_from_error(self, api_client, db_session, attachments_dir):
        budget, account = await _setup(api_client, db_session)
        job_id = (await _submit(api_client, budget, account)).json()["id"]

        resp = await api_client.post(f"/api/v1/{budget.id}/ai/jobs/{job_id}/retry")
        assert resp.status_code == 400  # still queued

        job = await db_session.get(AIJob, uuid.UUID(job_id))
        job.status = "error"
        job.attempts = 3
        job.error = "boom"
        await db_session.flush()

        resp = await api_client.post(f"/api/v1/{budget.id}/ai/jobs/{job_id}/retry")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["attempts"] == 0
        assert body["error"] is None

    async def test_delete_removes_job_and_staging(
        self, api_client, db_session, attachments_dir
    ):
        budget, account = await _setup(api_client, db_session)
        body = (await _submit(api_client, budget, account)).json()
        job = await db_session.get(AIJob, uuid.UUID(body["id"]))
        staged = attachments_dir / job.payload["staged_path"]
        assert staged.exists()

        resp = await api_client.delete(f"/api/v1/{budget.id}/ai/jobs/{body['id']}")
        assert resp.status_code == 204
        assert not staged.exists()
        assert await db_session.get(AIJob, uuid.UUID(body["id"])) is None


class TestAIJobLinkOnCreate:
    async def _make_done_nl_job(self, db_session, budget) -> AIJob:
        job = AIJob(
            budget_id=budget.id,
            kind="nl_parse",
            status="done",
            payload={"text": "coffee 5.50"},
        )
        db_session.add(job)
        await db_session.flush()
        return job

    async def test_create_with_ai_job_id_links_and_stamps(self, api_client, db_session):
        budget, account = await _setup(api_client, db_session)
        job = await self._make_done_nl_job(db_session, budget)

        resp = await api_client.post(
            f"/api/v1/{budget.id}/transactions",
            json={
                "account_id": str(account.id),
                "date": "2026-08-02",
                "amount": "-5.50",
                "payee_name": "Starbucks",
                "approved": False,
                "ai_job_id": str(job.id),
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["created_via"] == "ai_nl"
        await db_session.refresh(job)
        assert str(job.transaction_id) == body["id"]

    async def test_cross_budget_ai_job_id_rejected(self, api_client, db_session):
        budget, account = await _setup(api_client, db_session)
        other_budget = await create_budget(db_session, api_client.test_user, name="Second")
        job = await self._make_done_nl_job(db_session, other_budget)

        resp = await api_client.post(
            f"/api/v1/{budget.id}/transactions",
            json={
                "account_id": str(account.id),
                "date": "2026-08-02",
                "amount": "-5.50",
                "ai_job_id": str(job.id),
            },
        )
        assert resp.status_code == 404

    async def test_created_via_not_settable_directly(self, api_client, db_session):
        budget, account = await _setup(api_client, db_session)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/transactions",
            json={
                "account_id": str(account.id),
                "date": "2026-08-02",
                "amount": "-5.50",
                "created_via": "ai_receipt",  # ignored — not a request field
            },
        )
        assert resp.status_code == 201
        assert resp.json()["created_via"] is None


class TestHasAttachmentFilter:
    async def test_budget_listing_filters_by_attachment(self, api_client, db_session):
        from datetime import date

        from igab.db.models import TransactionAttachment

        budget, account = await _setup(api_client, db_session)
        with_att = await create_transaction(
            db_session, budget, account, "-10.00", date(2026, 8, 1)
        )
        without_att = await create_transaction(
            db_session, budget, account, "-20.00", date(2026, 8, 1)
        )
        db_session.add(
            TransactionAttachment(
                transaction_id=with_att.id,
                filename="x.webp",
                original_filename="x.jpg",
                content_type="image/webp",
                file_size=10,
                storage_path=f"2026/08/01/{with_att.id}/x.webp",
            )
        )
        await db_session.flush()

        both = (await api_client.get(f"/api/v1/{budget.id}/transactions")).json()
        assert both["total_count"] == 2

        with_only = (
            await api_client.get(f"/api/v1/{budget.id}/transactions?has_attachment=true")
        ).json()
        assert with_only["total_count"] == 1
        assert with_only["transactions"][0]["id"] == str(with_att.id)

        without_only = (
            await api_client.get(f"/api/v1/{budget.id}/transactions?has_attachment=false")
        ).json()
        assert without_only["total_count"] == 1
        assert without_only["transactions"][0]["id"] == str(without_att.id)

    async def test_account_listing_filters_by_attachment(self, api_client, db_session):
        from datetime import date

        from igab.db.models import TransactionAttachment

        budget, account = await _setup(api_client, db_session)
        with_att = await create_transaction(
            db_session, budget, account, "-10.00", date(2026, 8, 1)
        )
        await create_transaction(db_session, budget, account, "-20.00", date(2026, 8, 1))
        db_session.add(
            TransactionAttachment(
                transaction_id=with_att.id,
                filename="y.webp",
                original_filename="y.jpg",
                content_type="image/webp",
                file_size=10,
                storage_path=f"2026/08/01/{with_att.id}/y.webp",
            )
        )
        await db_session.flush()

        rows = (
            await api_client.get(
                f"/api/v1/accounts/{account.id}/transactions?has_attachment=true"
            )
        ).json()
        assert [r["id"] for r in rows] == [str(with_att.id)]


class TestPDFAttachments:
    def make_pdf(self) -> bytes:
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "TOTAL $9.99")
        data = doc.tobytes()
        doc.close()
        return data

    async def test_upload_and_serve_pdf_attachment(
        self, api_client, db_session, attachments_dir
    ):
        from datetime import date

        budget, account = await _setup(api_client, db_session)
        txn = await create_transaction(db_session, budget, account, "-9.99", date(2026, 8, 1))

        resp = await api_client.post(
            f"/api/v1/transactions/{txn.id}/attachments",
            files={"file": ("bill.pdf", self.make_pdf(), "application/pdf")},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["content_type"] == "application/pdf"
        assert body["filename"].endswith(".pdf")

        full = await api_client.get(f"/api/v1/attachments/{body['id']}")
        assert full.status_code == 200
        assert full.headers["content-type"] == "application/pdf"
        assert full.content[:5] == b"%PDF-"

        thumb = await api_client.get(f"/api/v1/attachments/{body['id']}?thumbnail=true")
        assert thumb.status_code == 200
        assert thumb.headers["content-type"] == "image/webp"

    async def test_corrupt_pdf_rejected(self, api_client, db_session, attachments_dir):
        from datetime import date

        budget, account = await _setup(api_client, db_session)
        txn = await create_transaction(db_session, budget, account, "-9.99", date(2026, 8, 1))
        resp = await api_client.post(
            f"/api/v1/transactions/{txn.id}/attachments",
            files={"file": ("bad.pdf", b"%PDF-1.4 garbage", "application/pdf")},
        )
        assert resp.status_code >= 400

    async def test_submit_pdf_receipt_accepted(self, api_client, db_session, attachments_dir):
        budget, account = await _setup(api_client, db_session)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/ai/receipts",
            files={"file": ("bill.pdf", self.make_pdf(), "application/pdf")},
            data={"account_id": str(account.id)},
        )
        assert resp.status_code == 202, resp.text


class TestAttachmentPathStability:
    async def test_date_edit_does_not_orphan_file(
        self, api_client, db_session, attachments_dir
    ):
        """The pre-existing path bug: files were located by re-deriving the
        path from txn.date. With storage_path recorded at upload, editing the
        date must not break downloads."""
        from datetime import date

        from igab.repositories.attachment_repo import AttachmentRepository
        from igab.services.attachment_service import AttachmentService

        budget, account = await _setup(api_client, db_session)
        txn = await create_transaction(db_session, budget, account, "-10.00", date(2026, 8, 1))

        svc = AttachmentService(AttachmentRepository(db_session))
        attachment = await svc.upload(txn, tiny_jpeg(), "r.jpg", "image/jpeg")
        original_path = svc.get_file_path(attachment, txn)
        assert original_path.exists()

        txn.date = date(2026, 7, 15)  # simulate post-attach date correction
        await db_session.flush()
        assert svc.get_file_path(attachment, txn) == original_path
        assert svc.get_file_path(attachment, txn).exists()
