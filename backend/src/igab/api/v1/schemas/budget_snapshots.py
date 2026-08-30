from datetime import datetime

from pydantic import BaseModel


class SnapshotFile(BaseModel):
    """One kept snapshot, as the per-budget list shows it."""

    name: str
    size_bytes: int
    modified_at: datetime


class SnapshotCreated(BaseModel):
    name: str
    size_bytes: int
    budget_name: str
    exported_at: str
    #: Per table, so the UI can say what is in the file rather than only how
    #: big it is.
    row_counts: dict[str, int]
    #: Receipts are not carried in v1 (see snapshot_format.AttachmentSummary).
    #: Reported so the UI can say so before someone relies on it.
    attachments_omitted: int


class SnapshotInspection(BaseModel):
    """What a file says about itself, and whether this installation can read
    it. Mutates nothing — this is what makes "check before you restore" a
    real option rather than an encouragement."""

    format: str
    format_version: int
    alembic_revision: str
    app_version: str
    exported_at: str
    budget_name: str
    source_budget_id: str
    row_counts: dict[str, int]
    attachments_omitted: int
    ok: bool
    refusals: list[str]
    warnings: list[str]


class SnapshotImportResult(BaseModel):
    """What an import actually did.

    Returned rather than written to ``budgets.import_summary``: that column is
    validated as a YNABImportResult by the imports endpoint, and a
    snapshot-shaped dict there would 500 it.
    """

    budget_id: str
    budget_name: str
    row_counts: dict[str, int]
    attachments_omitted: int
    #: Restore only: receipts that could not be put back, because the
    #: transaction they hung on is not in the snapshot.
    attachments_dropped: int = 0
    warnings: list[str] = []
