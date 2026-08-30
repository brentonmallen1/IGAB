"""A file written last year still reads, and still means the same thing.

Parametrized over every directory in `tests/fixtures/`, so adding a fixture
adds coverage with no edit here.

Points 1-3 are the backwards-compatibility guarantee: a frozen file imports, a
frozen file produces the numbers it produced when it was written, and a schema
change that would make an old snapshot unreadable fails HERE — at the moment
it is made — rather than the first time someone reaches for a backup. Points
4-5 are the correctness one: today's writer still round-trips, and a file this
version cannot read is refused without touching anything.

Both live in one file so nobody adds a second, shorter version of either.

When one of these goes red, the fix is almost never to regenerate the fixture.
See tests/fixtures/exports/README.md.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from igab.db.models import Budget
from igab.domain.snapshot_format import check_compatibility
from igab.services import budget_snapshot

from .factories import make_services
from .invariants import assert_financial_invariants, assert_no_cross_budget_references

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
EXPORTS = FIXTURES / "exports"
SNAPSHOTS = FIXTURES / "snapshots"
EXPECTED = EXPORTS / "expected"


def _versions() -> list[str]:
    if not EXPORTS.exists():
        return []
    return sorted(d.name for d in EXPORTS.iterdir() if d.is_dir() and d.name != "expected")


VERSIONS = _versions()


def test_the_corpus_is_not_empty():
    """A format with no frozen fixture has no compatibility guarantee, and an
    empty corpus makes every test below vacuously pass."""
    assert VERSIONS, (
        "No fixtures in tests/fixtures/exports/. Capture one with "
        "`python scripts/capture_budget_fixtures.py --new` — a format nobody "
        "froze is a format nobody can promise to keep reading."
    )


@pytest.mark.parametrize("version", VERSIONS)
def test_every_version_has_all_three_pieces(version):
    assert (EXPORTS / version).is_dir()
    assert (SNAPSHOTS / version).is_dir(), f"{version} has an export but no snapshot"
    assert (EXPECTED / f"{version}.json").is_file(), f"{version} has no expected/*.json"


def _one(directory: Path) -> Path:
    files = sorted(directory.glob("*.zip"))
    assert files, f"{directory} holds no zip"
    return files[0]


class TestFrozenExportsStillImport:
    @pytest.mark.parametrize("version", VERSIONS)
    async def test_it_imports_and_means_what_it_meant(
        self, api_client, db_session, version
    ):
        """The numbers are the contract. `expected/<version>.json` is what the
        file produced when it was written, to the cent, month by month."""
        body = _one(EXPORTS / version).read_bytes()
        expected = json.loads((EXPECTED / f"{version}.json").read_text())

        resp = await api_client.post(
            "/api/v1/budgets/import-ynab",
            files={"file": ("export.zip", body, "application/zip")},
            data={"name": f"Compat {version}"},
        )
        assert resp.status_code in (200, 201), resp.text
        budget_id = resp.json()["budget"]["id"]

        services = make_services(db_session)
        from igab.repositories.category_repo import CategoryRepository

        named = await CategoryRepository(db_session).get_all_with_group_names(
            budget_id, include_hidden=True
        )
        names = {c.id: f"{g}: {c.name}" for c, g in named}

        mismatches: list[str] = []
        for month_iso, month_expected in expected["months"].items():
            from datetime import date

            month = date.fromisoformat(month_iso)
            summary = await services.budgets.get_budget_summary(budget_id, month)
            actual = {
                names[b.category_id]: [str(b.assigned), str(b.activity), str(b.available)]
                for b in summary.category_balances
                if b.category_id in names
            }
            for key, figures in month_expected["categories"].items():
                if key in actual and actual[key] != figures:
                    mismatches.append(f"{month_iso} {key}: {figures} -> {actual[key]}")

        assert not mismatches[:10], (
            f"{version} no longer produces the numbers it recorded:\n"
            + "\n".join(mismatches[:10])
            + "\n\nDo NOT edit the expected file to match. If a bug fix changed "
            "what an old export should mean, that is a deliberate diff and it "
            "belongs in a commit message."
        )


class TestFrozenSnapshotsStillImport:
    @pytest.mark.parametrize("version", VERSIONS)
    async def test_it_imports_as_a_new_budget(self, api_client, db_session, version):
        body = _one(SNAPSHOTS / version).read_bytes()
        resp = await api_client.post(
            "/api/v1/budgets/import-snapshot",
            files={"file": ("snapshot.igab.zip", body, "application/zip")},
            data={"name": f"Compat snapshot {version}"},
        )
        assert resp.status_code == 201, resp.text

        from uuid import UUID

        budget_id = UUID(resp.json()["budget_id"])
        await assert_financial_invariants(db_session, budget_id)
        await assert_no_cross_budget_references(db_session, budget_id)

    @pytest.mark.parametrize("version", VERSIONS)
    async def test_its_verdict_is_readable_never_refused(self, api_client, db_session, version):
        """The guarantee itself. A column added tomorrow may warn — a dropped
        one, a nullable one, a defaulted one — but it must never make a file
        this installation wrote unreadable."""
        path = _one(SNAPSHOTS / version)
        manifest = budget_snapshot.read_manifest(path)
        verdict = check_compatibility(
            manifest,
            current_revision=await budget_snapshot.current_revision(db_session),
            revision_history=budget_snapshot.migration_history(),
        )
        assert verdict.ok, (
            f"{version} can no longer be read: {list(verdict.refusals)}\n\n"
            "A schema change made an old snapshot unreadable. Either make the "
            "new column nullable or defaulted, or raise MIN_SUPPORTED_VERSION "
            "and delete the fixtures it orphans in the same commit."
        )


class TestTodaysWriterStillRoundTrips:
    """What the frozen files cannot catch: a bug in the writer as it is now."""

    async def test_a_snapshot_written_today_imports_today(self, api_client, db_session):
        from .full_budget import build_full_budget

        source = await build_full_budget(db_session, api_client.test_user)
        exported = await api_client.get(f"/api/v1/budgets/{source.id}/snapshot")
        assert exported.status_code == 200

        resp = await api_client.post(
            "/api/v1/budgets/import-snapshot",
            files={"file": ("s.igab.zip", exported.content, "application/zip")},
        )
        assert resp.status_code == 201, resp.text

    async def test_an_export_written_today_imports_today(self, api_client, db_session):
        from .full_budget import build_full_budget

        source = await build_full_budget(db_session, api_client.test_user)
        exported = await api_client.get(f"/api/v1/budgets/{source.id}/export?format=ynab")
        assert exported.status_code == 200

        resp = await api_client.post(
            "/api/v1/budgets/import-ynab",
            files={"file": ("e.zip", exported.content, "application/zip")},
            data={"name": "Round trip"},
        )
        assert resp.status_code in (200, 201), resp.text


class TestAFileThisVersionCannotRead:
    async def test_a_newer_format_version_is_refused_and_writes_nothing(
        self, api_client, db_session
    ):
        import io
        import zipfile

        body = _one(SNAPSHOTS / VERSIONS[-1]).read_bytes()
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(body)) as source, zipfile.ZipFile(out, "w") as target:
            for item in source.namelist():
                data = source.read(item)
                if item == "manifest.json":
                    manifest = json.loads(data)
                    manifest["format_version"] = 999
                    data = json.dumps(manifest).encode()
                target.writestr(item, data)

        before = (await db_session.execute(select(func.count()).select_from(Budget))).scalar_one()
        resp = await api_client.post(
            "/api/v1/budgets/import-snapshot",
            files={"file": ("s.igab.zip", out.getvalue(), "application/zip")},
        )
        assert resp.status_code == 400
        after = (await db_session.execute(select(func.count()).select_from(Budget))).scalar_one()
        assert after == before
