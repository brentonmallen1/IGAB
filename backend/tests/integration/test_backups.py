"""The backup command handoff, as the client sees it.

The agent is a separate container polling BACKUPS_DIR/.agent/command.json
every ~10s. POST /backups/run only writes that file — for up to a poll
interval nothing else observable changes, and `job` still describes the
PREVIOUS run. `queued` is the only honest signal in that window; without it
the UI couldn't tell "queued" from "idle" and a click looked like a no-op.
"""

import json
import os

import pytest

from igab.config import settings


@pytest.fixture
def backups_dir(tmp_path, monkeypatch):
    """A scratch BACKUPS_DIR with a live agent heartbeat."""
    agent = tmp_path / ".agent"
    agent.mkdir()
    (agent / "heartbeat").touch()
    monkeypatch.setattr(settings, "BACKUPS_DIR", str(tmp_path))
    return tmp_path


class TestRunBackup:
    async def test_run_queues_a_command_and_reports_it(self, api_client, backups_dir):
        before = (await api_client.get("/api/v1/backups")).json()
        assert before["agent_online"] is True
        assert before["queued"] is False

        resp = await api_client.post("/api/v1/backups/run")
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        command_path = backups_dir / ".agent" / "command.json"
        assert command_path.exists()
        assert json.loads(command_path.read_text())["id"] == job_id

        after = (await api_client.get("/api/v1/backups")).json()
        assert after["queued"] is True

        # /backups/status authenticates the raw token (DB-free, works
        # mid-restore), so the get_current_user override doesn't cover it.
        from igab.services.auth_service import create_access_token

        token = create_access_token(str(api_client.test_user.id))
        status = (
            await api_client.get(
                "/api/v1/backups/status", headers={"Authorization": f"Bearer {token}"}
            )
        ).json()
        assert status["queued"] is True

    async def test_second_run_while_queued_is_409(self, api_client, backups_dir):
        assert (await api_client.post("/api/v1/backups/run")).status_code == 200
        again = await api_client.post("/api/v1/backups/run")
        assert again.status_code == 409
        assert "already in progress" in again.json()["detail"]

    async def test_run_without_agent_is_409(self, api_client, backups_dir):
        os.remove(backups_dir / ".agent" / "heartbeat")
        resp = await api_client.post("/api/v1/backups/run")
        assert resp.status_code == 409
        assert "not running" in resp.json()["detail"]

    async def test_queued_clears_once_the_agent_takes_the_command(self, api_client, backups_dir):
        await api_client.post("/api/v1/backups/run")
        # The agent consumes command.json and writes status.json — emulate it.
        os.remove(backups_dir / ".agent" / "command.json")
        (backups_dir / ".agent" / "status.json").write_text(
            json.dumps({"id": "x", "action": "backup", "state": "running"})
        )
        body = (await api_client.get("/api/v1/backups")).json()
        assert body["queued"] is False
        assert body["job"]["state"] == "running"


class TestDownloadBackup:
    """Reading a backup needs the volume, not the agent.

    The agent makes backups; the API container mounts the same directory, so a
    download works while the agent is offline — which is exactly when someone
    wants their file off the server.
    """

    async def test_a_backup_downloads_byte_for_byte(self, api_client, backups_dir):
        name = "igab-20260829-120000.dump"
        (backups_dir / name).write_bytes(b"PGDMP-fictional-bytes")

        resp = await api_client.get(f"/api/v1/backups/{name}/download")
        assert resp.status_code == 200, resp.text
        assert resp.content == b"PGDMP-fictional-bytes"
        assert name in resp.headers["content-disposition"]

    async def test_an_encrypted_backup_downloads_too(self, api_client, backups_dir):
        """It is already encrypted; that is what it is for."""
        name = "igab-20260829-120000.dump.age"
        (backups_dir / name).write_bytes(b"age-encrypted")

        resp = await api_client.get(f"/api/v1/backups/{name}/download")
        assert resp.status_code == 200
        assert resp.content == b"age-encrypted"

    async def test_a_file_that_is_not_a_backup_is_not_served(self, api_client, backups_dir):
        """The listing decides what exists; a file that happens to sit in the
        directory is not a backup."""
        (backups_dir / "notes.txt").write_text("not a backup")

        resp = await api_client.get("/api/v1/backups/notes.txt/download")
        assert resp.status_code == 404

    @pytest.mark.parametrize("name", ["..%2F..%2Fetc%2Fpasswd", ".hidden.dump", "%20igab.dump"])
    async def test_a_name_that_is_a_path_is_refused(self, api_client, backups_dir, name):
        resp = await api_client.get(f"/api/v1/backups/{name}/download")
        assert resp.status_code in (400, 404)

    async def test_a_non_admin_is_refused(self, api_client, db_session, backups_dir):
        """Every /backups endpoint but the status probe is admin-gated, and
        the Settings section is hidden to match."""
        from .factories import create_user

        name = "igab-20260829-120000.dump"
        (backups_dir / name).write_bytes(b"x")
        ordinary = await create_user(db_session)

        from igab.dependencies import get_current_user
        from igab.main import app

        app.dependency_overrides[get_current_user] = lambda: ordinary
        resp = await api_client.get(f"/api/v1/backups/{name}/download")
        assert resp.status_code == 403


class TestTheJoinIsAsMuchOfTheRuleAsTheGuard:
    """CodeQL flagged the whole-app download and not its per-budget twin.

    Both built a path from a client-supplied name. Neither does now: the name
    chooses among files the server already listed, and the path comes from the
    directory scan. What is left for this helper to hold is the one thing a
    listing cannot — a symlink inside the volume pointing elsewhere.
    """

    def test_a_listed_name_lands_in_the_directory(self, tmp_path):
        from igab.services.backup_service import listed_backup_path

        path = listed_backup_path(tmp_path, "igab-20260829-120000.dump")
        assert path.parent == tmp_path.resolve()
        assert path.name == "igab-20260829-120000.dump"

    @pytest.mark.parametrize(
        "name",
        ["../etc/passwd", "..", "a/b.dump", "a\\b.dump", ".hidden.dump", " igab.dump", ""],
    )
    def test_a_name_that_is_a_path_never_reaches_a_listing(self, tmp_path, name):
        """The guard runs before the lookup, so a name like this is refused
        rather than compared against the directory."""
        from igab.domain.exceptions import InvariantViolation
        from igab.services.backup_service import safe_backup_filename

        with pytest.raises(InvariantViolation):
            safe_backup_filename(name)

    def test_a_symlink_out_of_the_directory_is_refused(self, tmp_path):
        """What the name check cannot see. Planting one needs write access to
        the volume, so it is no great escalation — but the check turns "no
        traversal is reachable" from an argument into a property."""
        from igab.domain.exceptions import InvariantViolation
        from igab.services.backup_service import listed_backup_path

        outside = tmp_path.parent / "outside.dump"
        outside.write_text("not yours")
        inside = tmp_path / "igab-20260829-120000.dump"
        inside.symlink_to(outside)

        with pytest.raises(InvariantViolation):
            listed_backup_path(tmp_path, "igab-20260829-120000.dump")

    def test_a_symlink_within_the_directory_is_fine(self, tmp_path):
        from igab.services.backup_service import listed_backup_path

        real = tmp_path / "real.dump"
        real.write_text("x")
        link = tmp_path / "igab-20260829-120000.dump"
        link.symlink_to(real)

        assert listed_backup_path(tmp_path, "igab-20260829-120000.dump") == real.resolve()
