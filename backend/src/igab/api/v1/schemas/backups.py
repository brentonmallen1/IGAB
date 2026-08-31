from datetime import datetime

from igab.api.v1.schemas.base import ApiModel


class BackupFile(ApiModel):
    name: str
    kind: str  # db | attachments | prerestore
    size_bytes: int
    modified_at: datetime
    encrypted: bool


class BackupJob(ApiModel):
    id: str | None = None
    action: str | None = None
    state: str | None = None  # running | done | error
    detail: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class BackupsOverview(ApiModel):
    agent_online: bool
    agent_last_seen: datetime | None
    maintenance: bool
    #: A command is written but the agent hasn't picked it up yet — it polls
    #: every ~10s, and `job` still describes the PREVIOUS job for that whole
    #: window. Without this the client can't tell "queued" from "idle", so a
    #: click on Back up now looked like it did nothing.
    queued: bool
    job: BackupJob | None
    files: list[BackupFile]


class BackupStatus(ApiModel):
    agent_online: bool
    maintenance: bool
    queued: bool
    job: BackupJob | None


class RestoreRequest(ApiModel):
    file: str
    pre_backup: bool = True
    # Deliberate speed bump: the client must assert the user confirmed a
    # destructive, data-replacing action.
    confirm: bool = False


class JobStarted(ApiModel):
    job_id: str
