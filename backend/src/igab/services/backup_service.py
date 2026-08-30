"""Backup listing and restore orchestration.

The actual pg_dump/pg_restore work happens in the db-backup container
("the agent", scripts/db-backup.sh) — it has the matching postgres client
tools and the /backups volume. The API talks to it through files in
BACKUPS_DIR/.agent/ rather than the database, because during a restore the
database is exactly the thing being replaced:

    heartbeat      touched by the agent every poll; freshness = "agent online"
    command.json   written (atomically) by the API to request a job
    status.json    written by the agent as the job progresses; survives
                   restarts so the outcome is readable after the API returns

While a restore runs the API enters maintenance mode: scheduler and AI
worker stopped, DB engine disposed, every API route except the backup
status endpoint answering 503. When the agent reports a terminal state the
process exits so the container restarts onto the restored database (and
re-runs Alembic migrations, in case the dump predates the current schema).
"""

import asyncio
import contextlib
import json
import os
import re
import signal
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from igab.config import settings
from igab.domain.exceptions import InvariantViolation

AGENT_DIR = ".agent"
HEARTBEAT_STALE_S = 30
# A restore that takes longer than this is assumed wedged; restart anyway so
# the app doesn't stay in maintenance mode forever.
RESTORE_WATCH_TIMEOUT_S = 15 * 60

_DUMP_RE = re.compile(r"^igab-(prerestore-)?\d{8}-\d{6}\.dump(\.age)?$")
_ATTACH_RE = re.compile(r"^igab-attachments-\d{8}-\d{6}\.tar\.gz(\.age)?$")

_state: dict[str, Any] = {"maintenance": False, "watcher": None}


def maintenance_active() -> bool:
    return bool(_state["maintenance"])


def _backups_dir() -> str:
    return settings.BACKUPS_DIR


def _agent_path(name: str) -> str:
    return os.path.join(_backups_dir(), AGENT_DIR, name)


def safe_backup_filename(name: str) -> str:
    """A name that arrived over HTTP, proven to be a filename and not a path.

    One implementation, because this guard is now needed by the restore
    endpoint, the whole-app download, and every per-budget snapshot route —
    and a path-traversal check written six times is a path-traversal check
    that is wrong in one of them. Raises InvariantViolation, which the app
    already answers with a 400.
    """
    if not name or name != name.strip():
        raise InvariantViolation("Invalid file name")
    if "/" in name or "\\" in name or "\x00" in name:
        raise InvariantViolation("Invalid file name")
    if name.startswith(".") or ".." in name:
        raise InvariantViolation("Invalid file name")
    return name


def resolved_backup_path(directory: str | Path, name: str) -> Path:
    """The file a client named, inside ``directory`` and provably nowhere else.

    The guard above proves a name is not a path. This proves the *join* lands
    where it should, which is a separate claim and was being made twice — here
    and in budget_snapshot.snapshot_path — with only the first half checked.
    One of those two was flagged by CodeQL and the other was not, which is a
    fair description of why a rule with two implementations is a bug waiting.

    Resolving both sides also closes what the name check cannot see: a symlink
    inside the backups volume pointing somewhere else entirely. That needs
    write access to the volume to plant, so it is not much of an escalation —
    but the check costs one comparison and turns "no traversal is reachable"
    from an argument into a property.
    """
    base = Path(directory).resolve()
    candidate = (base / safe_backup_filename(name)).resolve()
    if not candidate.is_relative_to(base):
        raise InvariantViolation("Invalid file name")
    return candidate


def _classify(name: str) -> str | None:
    if _ATTACH_RE.match(name):
        return "attachments"
    m = _DUMP_RE.match(name)
    if m:
        return "prerestore" if m.group(1) else "db"
    return None


def list_backup_files() -> list[dict]:
    try:
        entries = list(os.scandir(_backups_dir()))
    except OSError:
        return []
    files = []
    for entry in entries:
        kind = _classify(entry.name)
        if kind is None or not entry.is_file():
            continue
        stat = entry.stat()
        files.append(
            {
                "name": entry.name,
                "kind": kind,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                "encrypted": entry.name.endswith(".age"),
            }
        )
    files.sort(key=lambda f: f["modified_at"], reverse=True)
    return files


def agent_status() -> tuple[bool, datetime | None]:
    try:
        mtime = os.stat(_agent_path("heartbeat")).st_mtime
    except OSError:
        return False, None
    last_seen = datetime.fromtimestamp(mtime, tz=UTC)
    online = (datetime.now(tz=UTC) - last_seen).total_seconds() <= HEARTBEAT_STALE_S
    return online, last_seen


def read_job_status() -> dict | None:
    try:
        with open(_agent_path("status.json")) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def command_pending() -> bool:
    return os.path.exists(_agent_path("command.json"))


def job_running() -> bool:
    if command_pending():
        return True
    status = read_job_status()
    if status is not None and status.get("state") == "running":
        online, _ = agent_status()
        return online  # a dead agent's stale "running" shouldn't block forever
    return False


def write_command(action: str, file: str | None = None, pre_backup: bool = False) -> str:
    job_id = uuid.uuid4().hex
    command = {"id": job_id, "action": action, "file": file, "pre_backup": pre_backup}
    os.makedirs(os.path.dirname(_agent_path("command.json")), exist_ok=True)
    tmp = _agent_path(f".command-{job_id}.tmp")
    with open(tmp, "w") as f:
        json.dump(command, f)
    os.replace(tmp, _agent_path("command.json"))
    return job_id


async def enter_maintenance_and_watch() -> None:
    """Quiesce the app for a restore, then restart once the agent finishes.

    Stops background DB users and disposes the pool so the agent can
    terminate every connection without the API racing new ones in. The
    watcher exits the process on a terminal status — docker's restart
    policy boots the app fresh against the restored database.
    """
    from igab.db.session import engine
    from igab.tasks.ai_worker import ai_worker
    from igab.tasks.scheduler import stop_scheduler

    _state["maintenance"] = True
    await ai_worker.stop()
    stop_scheduler()
    await engine.dispose()
    _state["watcher"] = asyncio.create_task(_watch_restore())


async def _watch_restore() -> None:
    deadline = asyncio.get_event_loop().time() + RESTORE_WATCH_TIMEOUT_S
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(2)
        status = read_job_status()
        if status is not None and status.get("state") in ("done", "error"):
            break
    # Brief grace so the response/poll in flight can flush, then hard-exit;
    # the container restart runs migrations and boots clean either way.
    await asyncio.sleep(1)
    # Exiting this process alone is not enough when uvicorn runs with
    # --reload: the reloader parent owns the listening socket and would keep
    # accepting (and never answering) connections. Terminate the parent chain
    # (reloader or `uv run` wrapper) so the container's CMD actually ends.
    ppid = os.getppid()
    if ppid > 1:
        with contextlib.suppress(OSError):
            os.kill(ppid, signal.SIGTERM)
        await asyncio.sleep(1)
    os._exit(0)
