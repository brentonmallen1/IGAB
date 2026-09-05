"""Attachments are visible to ⌘Z.

Deleting a receipt used to unlink the bytes in the same request —
irreversible by construction. The row soft-deletes now (files stay for the
sweep's grace period), so undo brings the receipt back whole; past the
grace period the sweep purges row and files together, and undo meets an
honest "no longer exists" instead of a broken image. Rotation is a lossless
transpose, so its undo is the complementary rotation re-run through the
same service — pixels, thumbnail and metadata all follow.
"""

from datetime import UTC, date, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select

import igab.config
from igab.db.models import TransactionAttachment
from igab.tasks.attachment_sweep import DELETED_TXN_GRACE_DAYS, sweep_soft_deleted_attachments

from .factories import create_account, create_budget, create_transaction


@pytest.fixture
def attachments_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(igab.config.settings, "ATTACHMENTS_DIR", str(tmp_path))
    return tmp_path


def _png(width=40, height=20) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, "PNG")
    return buf.getvalue()


async def _setup(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    txn = await create_transaction(db_session, budget, account, "-42", date(2026, 8, 15))
    await db_session.commit()
    return budget, txn


async def _upload(api_client, txn):
    r = await api_client.post(
        f"/api/v1/transactions/{txn.id}/attachments",
        files={"file": ("receipt.png", _png(), "image/png")},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _undo(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text
    return r.json()


async def _listed(api_client, txn):
    return (await api_client.get(f"/api/v1/transactions/{txn.id}/attachments")).json()


class TestAttachmentUndo:
    async def test_upload_undoes_away_and_redoes_back(
        self, db_session, api_client, attachments_dir
    ):
        budget, txn = await _setup(db_session, api_client)
        uploaded = await _upload(api_client, txn)

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("attachment", "create")
        assert await _listed(api_client, txn) == []

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        assert [a["id"] for a in await _listed(api_client, txn)] == [uploaded["id"]]

    async def test_delete_undo_brings_the_receipt_back_whole(
        self, db_session, api_client, attachments_dir
    ):
        budget, txn = await _setup(db_session, api_client)
        uploaded = await _upload(api_client, txn)
        r = await api_client.delete(f"/api/v1/attachments/{uploaded['id']}")
        assert r.status_code == 204
        assert await _listed(api_client, txn) == []

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("attachment", "delete")
        [restored] = await _listed(api_client, txn)
        assert restored["id"] == uploaded["id"]
        # The bytes were never unlinked, so the image still serves.
        r = await api_client.get(f"/api/v1/attachments/{uploaded['id']}")
        assert r.status_code == 200

    async def test_rotate_undoes_by_rotating_back(self, db_session, api_client, attachments_dir):
        budget, txn = await _setup(db_session, api_client)
        uploaded = await _upload(api_client, txn)  # 40x20
        r = await api_client.post(
            f"/api/v1/attachments/{uploaded['id']}/rotate", json={"degrees": 90}
        )
        assert r.status_code == 200, r.text
        assert (r.json()["width"], r.json()["height"]) == (20, 40)

        undone = await _undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("attachment", "update")
        [after] = await _listed(api_client, txn)
        assert (after["width"], after["height"]) == (40, 20)

        r = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
        assert r.status_code == 200, r.text
        [redone] = await _listed(api_client, txn)
        assert (redone["width"], redone["height"]) == (20, 40)

    async def test_past_the_grace_period_undo_meets_an_honest_conflict(
        self, db_session, api_client, attachments_dir
    ):
        budget, txn = await _setup(db_session, api_client)
        uploaded = await _upload(api_client, txn)
        r = await api_client.delete(f"/api/v1/attachments/{uploaded['id']}")
        assert r.status_code == 204

        # Age the deletion past the grace period and let the sweep collect it.
        row = (
            await db_session.execute(
                select(TransactionAttachment).where(
                    TransactionAttachment.id == uploaded["id"],
                )
            )
        ).scalar_one()
        row.deleted_at = datetime.now(UTC) - timedelta(days=DELETED_TXN_GRACE_DAYS + 1)
        await db_session.commit()
        assert await sweep_soft_deleted_attachments(db_session) == 1

        r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert r.status_code == 409, r.text
