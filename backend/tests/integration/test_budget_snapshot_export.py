"""Exporting one budget: what lands in the file, and who may ask for it.

The export half of budget snapshots. Import is a separate stage, so what is
provable here is that the file holds this budget and only this budget, that
what it claims in its manifest is what it carries, and that the endpoints
around it are gated the way the design says.

The row counts come from budget_rows.row_counts — the same derived walk the
delete test uses — so a table added next month is checked here without anyone
editing this file.
"""

import io
import json
import zipfile
from decimal import Decimal

import pytest

from igab.config import settings
from igab.domain.snapshot_format import (
    FORMAT,
    SNAPSHOT_OMITTED,
    VERSION,
    carried_tables,
)
from igab.services import budget_snapshot

from .budget_rows import assert_fully_populated, row_counts
from .factories import add_budget_member, create_user
from .full_budget import build_full_budget, mark_snapshot_cache_valid


@pytest.fixture
def snapshot_store(tmp_path, monkeypatch):
    """A scratch BACKUPS_DIR, so kept snapshots do not need the real volume."""
    monkeypatch.setattr(settings, "BACKUPS_DIR", str(tmp_path))
    return tmp_path


def _archive(body: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(body))


def _manifest(body: bytes) -> dict:
    with _archive(body) as archive:
        return json.loads(archive.read("manifest.json"))


def _rows(body: bytes, table: str) -> list[dict]:
    with _archive(body) as archive:
        raw = archive.read(f"tables/{table}.ndjson").decode()
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


async def _download(api_client, budget_id) -> bytes:
    resp = await api_client.get(f"/api/v1/budgets/{budget_id}/snapshot")
    assert resp.status_code == 200, resp.text
    return resp.content


class TestTheFileHoldsTheBudget:
    async def test_every_carried_table_is_a_member_with_its_rows(self, api_client, db_session):
        full = await build_full_budget(db_session, api_client.test_user)
        await mark_snapshot_cache_valid(db_session, full.id)
        counts = await row_counts(db_session, full.id)
        assert_fully_populated(counts)

        body = await _download(api_client, full.id)
        manifest = _manifest(body)

        with _archive(body) as archive:
            members = set(archive.namelist())
        for table in carried_tables():
            assert f"tables/{table.name}.ndjson" in members, table.name
            assert manifest["row_counts"][table.name] == counts[table.name], table.name
            assert len(_rows(body, table.name)) == counts[table.name], table.name

    async def test_the_manifest_says_what_it_is(self, api_client, db_session):
        full = await build_full_budget(db_session, api_client.test_user)
        manifest = _manifest(await _download(api_client, full.id))
        assert manifest["format"] == FORMAT
        assert manifest["format_version"] == VERSION
        assert manifest["source_budget_id"] == str(full.id)
        assert manifest["budget_name"] == full.budget.name

    async def test_omitted_tables_are_absent_and_say_why(self, api_client, db_session):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _download(api_client, full.id)
        manifest = _manifest(body)
        with _archive(body) as archive:
            members = set(archive.namelist())
        for name, reason in SNAPSHOT_OMITTED.items():
            assert f"tables/{name}.ndjson" not in members, name
            assert manifest["omitted_tables"][name] == reason

    async def test_receipts_are_counted_not_carried(self, api_client, db_session):
        """The bytes are not in the file, and two budgets sharing one
        storage_path means deleting either destroys the other's receipt."""
        full = await build_full_budget(db_session, api_client.test_user)
        manifest = _manifest(await _download(api_client, full.id))
        assert manifest["attachments"]["included"] is False
        assert manifest["attachments"]["omitted_count"] == 1

    async def test_another_budgets_rows_are_not_in_the_file(self, api_client, db_session):
        mine = await build_full_budget(db_session, api_client.test_user)
        theirs = await build_full_budget(db_session, api_client.test_user)

        exported = {r["id"] for r in _rows(await _download(api_client, mine.id), "transactions")}
        assert exported
        for txn_id in theirs.transaction_ids:
            assert str(txn_id) not in exported

    async def test_money_is_written_as_a_string(self, api_client, db_session):
        """A float here is a rounding error someone restores a year later."""
        full = await build_full_budget(db_session, api_client.test_user)
        rows = _rows(await _download(api_client, full.id), "transactions")
        amounts = [r["amount"] for r in rows]
        assert amounts
        assert all(isinstance(a, str) for a in amounts)
        assert Decimal("-50.0000") in [Decimal(a) for a in amounts]

    async def test_rows_are_ordered_so_two_exports_diff(self, api_client, db_session):
        full = await build_full_budget(db_session, api_client.test_user)
        first = _rows(await _download(api_client, full.id), "transactions")
        second = _rows(await _download(api_client, full.id), "transactions")
        assert [r["id"] for r in first] == [r["id"] for r in second]
        assert [r["id"] for r in first] == sorted(r["id"] for r in first)

    async def test_the_ids_with_no_foreign_key_survive(self, api_client, db_session):
        """scheduled_transaction_id and import_batch_id have no FK to declare
        them; they must still be in the file for import to remap."""
        full = await build_full_budget(db_session, api_client.test_user)
        rows = _rows(await _download(api_client, full.id), "transactions")
        assert str(full.scheduled_id) in {r["scheduled_transaction_id"] for r in rows}
        assert str(full.import_batch_id) in {r["import_batch_id"] for r in rows}

    async def test_soft_deleted_rows_are_carried(self, api_client, db_session):
        """Undo restores them, so a snapshot that drops them loses history the
        app promises."""
        full = await build_full_budget(db_session, api_client.test_user)
        rows = _rows(await _download(api_client, full.id), "transactions")
        assert any(r["is_deleted"] for r in rows)


class TestKeepingSnapshots:
    async def test_created_snapshots_are_listed_and_downloadable(
        self, api_client, db_session, snapshot_store
    ):
        full = await build_full_budget(db_session, api_client.test_user)

        created = await api_client.post(f"/api/v1/budgets/{full.id}/snapshots")
        assert created.status_code == 201, created.text
        name = created.json()["name"]
        assert name.endswith(".igab.zip")
        assert created.json()["row_counts"]["transactions"] > 0

        listed = await api_client.get(f"/api/v1/budgets/{full.id}/snapshots")
        assert [f["name"] for f in listed.json()] == [name]

        downloaded = await api_client.get(f"/api/v1/budgets/{full.id}/snapshots/{name}")
        assert downloaded.status_code == 200
        assert _manifest(downloaded.content)["source_budget_id"] == str(full.id)

        deleted = await api_client.delete(f"/api/v1/budgets/{full.id}/snapshots/{name}")
        assert deleted.status_code == 204
        assert (await api_client.get(f"/api/v1/budgets/{full.id}/snapshots")).json() == []

    async def test_the_list_is_this_budgets_only(self, api_client, db_session, snapshot_store):
        """The whole point. The global backups list could never do this."""
        mine = await build_full_budget(db_session, api_client.test_user)
        theirs = await build_full_budget(db_session, api_client.test_user)
        await api_client.post(f"/api/v1/budgets/{mine.id}/snapshots")

        assert len((await api_client.get(f"/api/v1/budgets/{mine.id}/snapshots")).json()) == 1
        assert (await api_client.get(f"/api/v1/budgets/{theirs.id}/snapshots")).json() == []

    async def test_a_failed_export_leaves_nothing_in_the_list(
        self, api_client, db_session, snapshot_store, monkeypatch
    ):
        full = await build_full_budget(db_session, api_client.test_user)

        async def boom(*args, **kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(budget_snapshot, "export_budget_snapshot", boom)
        with pytest.raises(RuntimeError):
            await api_client.post(f"/api/v1/budgets/{full.id}/snapshots")

        assert budget_snapshot.list_snapshots(full.id) == []

    @pytest.mark.parametrize(
        "name",
        ["../../etc/passwd", "..%2Fx.igab.zip", ".hidden.igab.zip", "igab.dump"],
    )
    async def test_a_name_that_is_a_path_is_refused(
        self, api_client, db_session, snapshot_store, name
    ):
        full = await build_full_budget(db_session, api_client.test_user)
        resp = await api_client.get(f"/api/v1/budgets/{full.id}/snapshots/{name}")
        assert resp.status_code in (400, 404), resp.text

    async def test_deleting_a_snapshot_that_is_not_there_is_a_404(
        self, api_client, db_session, snapshot_store
    ):
        full = await build_full_budget(db_session, api_client.test_user)
        resp = await api_client.delete(
            f"/api/v1/budgets/{full.id}/snapshots/nothing-20260829-000000.igab.zip"
        )
        assert resp.status_code == 404


class TestInspect:
    async def test_a_file_this_app_wrote_reads_clean(self, api_client, db_session):
        full = await build_full_budget(db_session, api_client.test_user)
        body = await _download(api_client, full.id)

        resp = await api_client.post(
            "/api/v1/budgets/snapshot/inspect",
            files={"file": ("snapshot.igab.zip", body, "application/zip")},
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()
        assert result["ok"] is True
        assert result["refusals"] == []
        assert result["budget_name"] == full.budget.name
        assert result["row_counts"]["transactions"] > 0

    async def test_a_newer_format_is_refused_and_nothing_is_written(self, api_client, db_session):
        full = await build_full_budget(db_session, api_client.test_user)
        before = await row_counts(db_session, full.id)
        body = _rewritten_manifest(await _download(api_client, full.id), format_version=99)

        resp = await api_client.post(
            "/api/v1/budgets/snapshot/inspect",
            files={"file": ("snapshot.igab.zip", body, "application/zip")},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert any("v99" in r for r in resp.json()["refusals"])
        assert await row_counts(db_session, full.id) == before

    async def test_something_that_is_not_a_zip_is_a_sentence_not_a_traceback(self, api_client):
        resp = await api_client.post(
            "/api/v1/budgets/snapshot/inspect",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400
        assert "not a zip" in resp.json()["detail"]

    async def test_a_zip_with_no_manifest_is_refused(self, api_client):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("tables/accounts.ndjson", "")
        resp = await api_client.post(
            "/api/v1/budgets/snapshot/inspect",
            files={"file": ("x.igab.zip", buffer.getvalue(), "application/zip")},
        )
        assert resp.status_code == 400
        assert "manifest" in resp.json()["detail"]


class TestWhoMayExport:
    async def test_a_member_who_is_not_the_owner_is_refused(self, api_client, db_session):
        """A snapshot is the input to 'create a budget I own holding your
        data' — the same class of decision as deleting a budget."""
        full = await build_full_budget(db_session, api_client.test_user)
        member = await create_user(db_session)
        await add_budget_member(db_session, full.budget, member)

        from igab.dependencies import get_current_user
        from igab.main import app

        app.dependency_overrides[get_current_user] = lambda: member
        resp = await api_client.get(f"/api/v1/budgets/{full.id}/snapshot")
        assert resp.status_code == 403

    async def test_a_stranger_gets_a_404(self, api_client, db_session):
        full = await build_full_budget(db_session, api_client.test_user)
        stranger = await create_user(db_session)

        from igab.dependencies import get_current_user
        from igab.main import app

        app.dependency_overrides[get_current_user] = lambda: stranger
        resp = await api_client.get(f"/api/v1/budgets/{full.id}/snapshot")
        assert resp.status_code == 404

    async def test_a_member_may_still_list(self, api_client, db_session, snapshot_store):
        full = await build_full_budget(db_session, api_client.test_user)
        member = await create_user(db_session)
        await add_budget_member(db_session, full.budget, member)

        from igab.dependencies import get_current_user
        from igab.main import app

        app.dependency_overrides[get_current_user] = lambda: member
        resp = await api_client.get(f"/api/v1/budgets/{full.id}/snapshots")
        assert resp.status_code == 200


def _rewritten_manifest(body: bytes, **overrides) -> bytes:
    """The same archive with a hand-edited manifest — what a curious person
    with a zip tool would produce."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(body)) as source, zipfile.ZipFile(out, "w") as target:
        for item in source.namelist():
            data = source.read(item)
            if item == "manifest.json":
                manifest = json.loads(data)
                manifest.update(overrides)
                data = json.dumps(manifest).encode()
            target.writestr(item, data)
    return out.getvalue()
