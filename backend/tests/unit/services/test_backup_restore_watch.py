"""Which status ends the wait for a restore.

The incident: a restore was requested, the API restarted ~2s later while the
agent had not yet picked the command up, Alembic ran against the *pre*-restore
database, and the restore then rolled the schema and `alembic_version` back
underneath the running app. Nothing migrated it afterwards, so every bank sync
crashed writing its own log row — a column the code had and the database did
not — and rolled the whole sync back with it.

`status.json` describing the PREVIOUS job for up to a poll interval is already
a known property of this handoff (see `tests/integration/test_backups.py`,
where it is why `queued` exists). The watcher was the one reader that did not
account for it.
"""

from igab.services.backup_service import restore_finished

JOB = "b8f2c1d4e5a6"
OTHER = "0a1b2c3d4e5f"


class TestRestoreFinished:
    def test_this_jobs_completion_ends_the_wait(self):
        assert restore_finished({"id": JOB, "state": "done"}, JOB) is True

    def test_this_jobs_failure_ends_the_wait(self):
        """A failed restore still restarts: the database may be half-replaced,
        and staying in maintenance mode forever helps nobody."""
        assert restore_finished({"id": JOB, "state": "error"}, JOB) is True

    def test_the_previous_jobs_completion_does_not(self):
        """The whole incident. The agent polls every ~10s; until it picks this
        command up, the file still holds the last job's terminal state."""
        assert restore_finished({"id": OTHER, "state": "done"}, JOB) is False

    def test_the_previous_jobs_failure_does_not(self):
        assert restore_finished({"id": OTHER, "state": "error"}, JOB) is False

    def test_this_job_still_running_does_not(self):
        assert restore_finished({"id": JOB, "state": "running"}, JOB) is False

    def test_no_status_file_yet_does_not(self):
        """A first-ever restore: nothing has written status.json at all."""
        assert restore_finished(None, JOB) is False

    def test_a_status_with_no_id_does_not(self):
        assert restore_finished({"state": "done"}, JOB) is False
