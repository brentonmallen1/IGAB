"""The unified import preview: one reader for "here is a budget file".

The import section on the budget selector promises a person can hand over
whatever budget file they hold — the server decides which importer it belongs
to. Born from a real misfile: a snapshot downloaded as
``<uuid>.igab (1).zip`` (the browser's duplicate rename defeats any suffix
check) fed to the YNAB importer, which answered "Register CSV not found".

The classification rule lives in ``snapshot_format.is_snapshot_manifest`` and
``parser.looks_like_ynab_export``; these tests pin the routing built on them.
"""

import io
import zipfile


async def _new_budget(api_client, name: str) -> str:
    resp = await api_client.post("/api/v1/budgets", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _preview(api_client, body: bytes, filename: str = "upload.zip"):
    return await api_client.post(
        "/api/v1/budgets/import/preview",
        files={"file": (filename, body, "application/zip")},
    )


class TestTheServerPicksTheImporter:
    async def test_a_snapshot_previews_as_a_snapshot(self, api_client, db_session):
        budget_id = await _new_budget(api_client, "Snapshot source")
        exported = await api_client.get(f"/api/v1/budgets/{budget_id}/snapshot")
        assert exported.status_code == 200

        # The browser's duplicate-download rename — the filename must not matter.
        resp = await _preview(api_client, exported.content, "abc123.igab (1).zip")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["kind"] == "snapshot"
        assert body["ynab"] is None
        assert body["snapshot"]["ok"] is True
        assert body["snapshot"]["budget_name"] == "Snapshot source"

    async def test_an_igab_ynab_shaped_export_previews_as_ynab(self, api_client, db_session):
        """The near-miss this endpoint almost shipped with: the YNAB-shaped
        export ALSO carries a manifest.json (saying igab.budget-export), so
        member presence alone would have routed it to the snapshot reader.
        The manifest's format field is the discriminator."""
        budget_id = await _new_budget(api_client, "Export source")
        exported = await api_client.get(f"/api/v1/budgets/{budget_id}/export?format=ynab")
        assert exported.status_code == 200

        resp = await _preview(api_client, exported.content)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["kind"] == "ynab"
        assert body["snapshot"] is None
        assert body["ynab"] is not None

    async def test_a_zip_that_is_neither_names_both_expectations(self, api_client, db_session):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("holiday-photos.txt", "not a budget")

        resp = await _preview(api_client, out.getvalue())
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "manifest.json" in detail
        assert "Register.csv" in detail

    async def test_a_non_zip_is_refused_plainly(self, api_client, db_session):
        resp = await _preview(api_client, b"this was never a zip")
        assert resp.status_code == 400
        assert "not a zip archive" in resp.json()["detail"]


class TestAMisfiledSnapshotIsNamedNotDescribed:
    async def test_the_ynab_importer_says_snapshot_not_missing_csv(self, api_client, db_session):
        """The original bug report, verbatim: a snapshot posted to
        /budgets/import-ynab used to answer "Register CSV not found in ZIP"."""
        budget_id = await _new_budget(api_client, "Misfiled")
        exported = await api_client.get(f"/api/v1/budgets/{budget_id}/snapshot")
        assert exported.status_code == 200

        resp = await api_client.post(
            "/api/v1/budgets/import-ynab",
            files={"file": ("s.igab (1).zip", exported.content, "application/zip")},
            data={"name": "Misfiled copy"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "snapshot" in detail
        assert "Register CSV not found" not in detail
