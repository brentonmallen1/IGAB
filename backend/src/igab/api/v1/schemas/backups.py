from datetime import datetime

from pydantic import BaseModel


class BackupFile(BaseModel):
    name: str
    kind: str  # db | attachments | prerestore
    size_bytes: int
    modified_at: datetime
    encrypted: bool


class BackupJob(BaseModel):
    id: str | None = None
    action: str | None = None
    state: str | None = None  # running | done | error
    detail: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class BackupsOverview(BaseModel):
    agent_online: bool
    agent_last_seen: datetime | None
    maintenance: bool
    job: BackupJob | None
    files: list[BackupFile]


class BackupStatus(BaseModel):
    agent_online: bool
    maintenance: bool
    job: BackupJob | None


class RestoreRequest(BaseModel):
    file: str
    pre_backup: bool = True
    # Deliberate speed bump: the client must assert the user confirmed a
    # destructive, data-replacing action.
    confirm: bool = False


class JobStarted(BaseModel):
    job_id: str
