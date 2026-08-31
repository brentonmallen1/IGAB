"""Restoring a snapshot over the budget it came from.

The other half of the file. Import-as-new makes a copy; this replaces what is
there and keeps the budget — the id, so sharing survives and every link that
holds one still resolves; the name, so the budget someone just picked out of a
list is still called that; and the membership, so a restore cannot un-share a
shared budget or lock its owner out.

The destructive one, so the confirmation is typing the budget's name.
"""

import io
import json
import zipfile
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from igab.config import settings
from igab.db.models import BudgetMember, BudgetSnapshotMeta
from igab.domain.snapshot_format import carried_tables
from igab.services import budget_snapshot

from .budget_rows import row_counts
from .factories import add_budget_member, create_transaction, create_user
from .full_budget import MONTH, build_full_budget, mark_snapshot_cache_valid
from .invariants import assert_financial_invariants, assert_no_cross_budget_references


@pytest.fixture
def snapshot_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BACKUPS_DIR", str(tmp_path))
    return tmp_path


async def _export(api_client, budget_id) -> bytes:
    resp = await api_client.get(f"/api/v1/budgets/{budget_id}/snapshot")
    assert resp.status_code == 200, resp.text
    return resp.content


async def _restore(api_client, budget_id, body: bytes, *, confirm: str, pre_snapshot=None):
    data = {"confirm_name": confirm}
    if pre_snapshot is not None:
        data["pre_snapshot"] = str(pre_snapshot).lower()
    return await api_client.post(
        f"/api/v1/budgets/{budget_id}/snapshot/restore",
        files={"file": ("snapshot.igab.zip", body, "application/zip")},
        data=data,
    )


def _table(name):
    from igab.db.models import Base

    return Base.metadata.tables[name]


class TestARestorePutsTheBudgetBack:
    async def test_work_done_after_the_export_is_undone(
        self, api_client, db_session, snapshot_store
    ):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        before = await row_counts(db_session, full.id)

        # Six more transactions, entered after the snapshot was taken.
        account_id = full.account_ids[0]
        accounts = _table("accounts")
        account = (
            await db_session.execute(select(accounts).where(accounts.c.id == account_id))
        ).one()
        for amount in ("-1.00", "-2.00", "-3.00", "-4.00", "-5.00", "-6.00"):
            await create_transaction(
                db_session, full.budget, account, amount, MONTH + timedelta(days=2)
            )
        assert (await row_counts(db_session, full.id))["transactions"] == (
            before["transactions"] + 6
        )

        resp = await _restore(api_client, full.id, body, confirm=full.budget.name)
        assert resp.status_code == 200, resp.text

        after = await row_counts(db_session, full.id)
        for name in {t.name for t in carried_tables()}:
            assert after[name] == before[name], name

    async def test_what_the_file_does_not_carry_does_not_come_back(
        self, api_client, db_session, snapshot_store
    ):
        """A restore clears the whole budget, and only what the snapshot holds
        is written again. Undo history and the AI queue are gone on purpose —
        undoing across a restore is meaningless, and the queue's payloads name
        staged files that no longer matter. The derived cache is gone so it
        rebuilds. Receipts are the exception, below."""
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        await mark_snapshot_cache_valid(db_session, full.id)

        await _restore(api_client, full.id, body, confirm=full.budget.name)

        after = await row_counts(db_session, full.id)
        for name in ("change_log", "ai_jobs", "category_month_snapshots", "budget_snapshot_meta"):
            assert after[name] == 0, name

    async def test_receipts_survive_a_restore(self, api_client, db_session, snapshot_store):
        """A snapshot does not carry the bytes, but the rows are still this
        budget's data and the transactions they hang on come back with the
        same ids. Deleting them would destroy the only link to files that are
        still on disk and still correct."""
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        before = await row_counts(db_session, full.id)
        assert before["transaction_attachments"] == 1

        resp = await _restore(api_client, full.id, body, confirm=full.budget.name)
        assert resp.json()["attachments_dropped"] == 0
        after = await row_counts(db_session, full.id)
        assert after["transaction_attachments"] == 1

    async def test_a_receipt_on_a_transaction_the_snapshot_predates_is_reported(
        self, api_client, db_session, snapshot_store
    ):
        """It has nothing left to hang on. The file it points at stays on
        disk — this deletes a row, not bytes — and the count is reported
        rather than swallowed."""
        from igab.db.models import TransactionAttachment

        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)

        accounts = _table("accounts")
        account = (
            await db_session.execute(select(accounts).where(accounts.c.id == full.account_ids[0]))
        ).one()
        newer = await create_transaction(db_session, full.budget, account, "-12.00", MONTH)
        db_session.add(
            TransactionAttachment(
                transaction_id=newer.id,
                filename="later.webp",
                original_filename="later.jpg",
                content_type="image/webp",
                file_size=99,
            )
        )
        await db_session.flush()

        resp = await _restore(api_client, full.id, body, confirm=full.budget.name)
        assert resp.json()["attachments_dropped"] == 1
        after = await row_counts(db_session, full.id)
        assert after["transaction_attachments"] == 1

    async def test_the_budget_keeps_its_id_and_its_name(
        self, api_client, db_session, snapshot_store
    ):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)

        resp = await _restore(api_client, full.id, body, confirm=full.budget.name)
        assert resp.json()["budget_id"] == str(full.id)
        assert resp.json()["budget_name"] == full.budget.name

    async def test_the_transaction_ids_are_the_same_ones(
        self, api_client, db_session, snapshot_store
    ):
        """`preserve`, not `remap`. Attachment paths on disk and anything else
        holding a transaction id still resolve after a restore."""
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        transactions = _table("transactions")

        await _restore(api_client, full.id, body, confirm=full.budget.name)

        after = set(
            (
                await db_session.execute(
                    select(transactions.c.id).where(transactions.c.budget_id == full.id)
                )
            )
            .scalars()
            .all()
        )
        assert set(full.transaction_ids) <= after

    async def test_sharing_survives(self, api_client, db_session, snapshot_store):
        """budget_members is the one table a restore leaves alone: it is
        authorization, and losing it locks someone out of their own budget."""
        full = await build_full_budget(db_session, api_client.test_user)
        extra = await create_user(db_session)
        await add_budget_member(db_session, full.budget, extra)
        body = await _export(api_client, full.id)

        before = sorted(
            (
                await db_session.execute(
                    select(BudgetMember.user_id, BudgetMember.role).where(
                        BudgetMember.budget_id == full.id
                    )
                )
            ).all()
        )
        await _restore(api_client, full.id, body, confirm=full.budget.name)
        after = sorted(
            (
                await db_session.execute(
                    select(BudgetMember.user_id, BudgetMember.role).where(
                        BudgetMember.budget_id == full.id
                    )
                )
            ).all()
        )
        assert after == before
        assert len(after) == 3

    async def test_the_bank_link_is_kept(self, api_client, db_session, snapshot_store):
        """The opposite of a duplicate: clearing the link here would silently
        break a working bank connection, which is why the rule is asked at
        import and not at export."""
        full = await build_full_budget(db_session, api_client.test_user)
        accounts = _table("accounts")
        await db_session.execute(
            accounts.update()
            .where(accounts.c.id == full.account_ids[0])
            .values(simplefin_account_id="acct-fictional-1", first_sync_complete=True)
        )
        body = await _export(api_client, full.id)

        await _restore(api_client, full.id, body, confirm=full.budget.name)

        row = (
            await db_session.execute(
                select(accounts.c.simplefin_account_id, accounts.c.first_sync_complete).where(
                    accounts.c.id == full.account_ids[0]
                )
            )
        ).one()
        assert row[0] == "acct-fictional-1"
        assert row[1] is True

    async def test_the_restored_budget_is_still_sound(self, api_client, db_session, snapshot_store):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        await _restore(api_client, full.id, body, confirm=full.budget.name)
        await assert_financial_invariants(db_session, full.id)
        await assert_no_cross_budget_references(db_session, full.id)

    async def test_the_derived_cache_is_cleared_so_it_rebuilds(
        self, api_client, db_session, snapshot_store
    ):
        """The delete pass takes the meta row, and nothing re-inserts it —
        absence *is* the invalidation. The hooks in db/invalidation would not
        have fired: they short-circuit on the Core statements used here."""
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        await mark_snapshot_cache_valid(db_session, full.id)

        await _restore(api_client, full.id, body, confirm=full.budget.name)

        meta = (
            await db_session.execute(
                select(func.count())
                .select_from(BudgetSnapshotMeta)
                .where(BudgetSnapshotMeta.budget_id == full.id)
            )
        ).scalar_one()
        assert meta == 0


class TestTheConfirmation:
    async def test_the_wrong_name_changes_nothing(self, api_client, db_session, snapshot_store):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        account = (
            await db_session.execute(
                select(_table("accounts")).where(_table("accounts").c.id == full.account_ids[0])
            )
        ).one()
        await create_transaction(db_session, full.budget, account, "-9.00", MONTH)
        before = await row_counts(db_session, full.id)

        resp = await _restore(api_client, full.id, body, confirm="not the name")
        assert resp.status_code == 400
        assert "Type the budget's name" in resp.json()["detail"]
        assert await row_counts(db_session, full.id) == before

    async def test_the_right_name_with_surrounding_space_is_accepted(
        self, api_client, db_session, snapshot_store
    ):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        resp = await _restore(api_client, full.id, body, confirm=f"  {full.budget.name} ")
        assert resp.status_code == 200


class TestTheSafetyCopy:
    async def test_a_copy_is_kept_before_the_restore(self, api_client, db_session, snapshot_store):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        assert budget_snapshot.list_snapshots(full.id) == []

        await _restore(api_client, full.id, body, confirm=full.budget.name)

        kept = budget_snapshot.list_snapshots(full.id)
        assert len(kept) == 1

    async def test_an_unwritable_backups_volume_is_a_409_and_not_a_warning(
        self, api_client, db_session, monkeypatch, tmp_path
    ):
        """A silent no-op here is the trust failure the whole feature exists
        to prevent."""
        full = await build_full_budget(db_session, api_client.test_user)
        monkeypatch.setattr(settings, "BACKUPS_DIR", str(tmp_path))
        body = await _export(api_client, full.id)
        before = await row_counts(db_session, full.id)

        def refuse(*args, **kwargs):
            raise OSError("read-only file system")

        monkeypatch.setattr(budget_snapshot.Path, "mkdir", refuse)

        resp = await _restore(api_client, full.id, body, confirm=full.budget.name)
        assert resp.status_code == 409
        assert "could not be saved" in resp.json()["detail"]
        assert await row_counts(db_session, full.id) == before

    async def test_the_copy_can_be_declined(self, api_client, db_session, snapshot_store):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        resp = await _restore(
            api_client, full.id, body, confirm=full.budget.name, pre_snapshot=False
        )
        assert resp.status_code == 200
        assert budget_snapshot.list_snapshots(full.id) == []


class TestAForeignSnapshot:
    async def test_restoring_another_budgets_file_remaps_rather_than_colliding(
        self, api_client, db_session, snapshot_store
    ):
        """Preserving ids here would collide with the source budget's live
        rows on the primary key. The rule is asked once, in plan_for: did this
        file leave the budget it is landing in?"""
        source = await build_full_budget(db_session, api_client.test_user)
        target = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, source.id)

        resp = await _restore(api_client, target.id, body, confirm=target.budget.name)
        assert resp.status_code == 200, resp.text

        transactions = _table("transactions")
        landed = set(
            (
                await db_session.execute(
                    select(transactions.c.id).where(transactions.c.budget_id == target.id)
                )
            )
            .scalars()
            .all()
        )
        assert landed
        assert not landed & set(source.transaction_ids)
        assert (await row_counts(db_session, source.id))["transactions"] > 0
        await assert_no_cross_budget_references(db_session, target.id)
        await assert_no_cross_budget_references(db_session, source.id)

    async def test_a_foreign_snapshot_drops_its_bank_link(
        self, api_client, db_session, snapshot_store
    ):
        source = await build_full_budget(db_session, api_client.test_user)
        accounts = _table("accounts")
        await db_session.execute(
            accounts.update()
            .where(accounts.c.id == source.account_ids[0])
            .values(simplefin_account_id="acct-fictional-2")
        )
        target = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, source.id)

        await _restore(api_client, target.id, body, confirm=target.budget.name)

        links = (
            (
                await db_session.execute(
                    select(accounts.c.simplefin_account_id).where(accounts.c.budget_id == target.id)
                )
            )
            .scalars()
            .all()
        )
        assert all(link is None for link in links)


class TestWhoMayRestore:
    async def test_a_member_who_is_not_the_owner_is_refused(
        self, api_client, db_session, snapshot_store
    ):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        member = await create_user(db_session)
        await add_budget_member(db_session, full.budget, member)

        from igab.dependencies import get_current_user
        from igab.main import app

        app.dependency_overrides[get_current_user] = lambda: member
        resp = await _restore(api_client, full.id, body, confirm=full.budget.name)
        assert resp.status_code == 403

    async def test_a_stranger_gets_a_404(self, api_client, db_session, snapshot_store):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _export(api_client, full.id)
        stranger = await create_user(db_session)

        from igab.dependencies import get_current_user
        from igab.main import app

        app.dependency_overrides[get_current_user] = lambda: stranger
        resp = await _restore(api_client, full.id, body, confirm=full.budget.name)
        assert resp.status_code == 404


class TestARefusedFileChangesNothing:
    async def test_a_newer_format_version_leaves_the_budget_alone(
        self, api_client, db_session, snapshot_store
    ):
        full = await build_full_budget(db_session, api_client.test_user)
        before = await row_counts(db_session, full.id)
        body = await _export(api_client, full.id)

        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(body)) as source, zipfile.ZipFile(out, "w") as target:
            for item in source.namelist():
                data = source.read(item)
                if item == "manifest.json":
                    manifest = json.loads(data)
                    manifest["format_version"] = 99
                    data = json.dumps(manifest).encode()
                target.writestr(item, data)

        resp = await _restore(api_client, full.id, out.getvalue(), confirm=full.budget.name)
        assert resp.status_code == 400
        assert await row_counts(db_session, full.id) == before
        assert budget_snapshot.list_snapshots(full.id) == []
