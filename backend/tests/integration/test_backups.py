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

    async def test_queued_clears_once_the_agent_takes_the_command(
        self, api_client, backups_dir
    ):
        await api_client.post("/api/v1/backups/run")
        # The agent consumes command.json and writes status.json — emulate it.
        os.remove(backups_dir / ".agent" / "command.json")
        (backups_dir / ".agent" / "status.json").write_text(
            json.dumps({"id": "x", "action": "backup", "state": "running"})
        )
        body = (await api_client.get("/api/v1/backups")).json()
        assert body["queued"] is False
        assert body["job"]["state"] == "running"
