"""The scheduled budget-snapshot job.

A budget snapshot is the portable, per-budget copy — the one worth having
before a risky import and the only one that survives moving to another
machine — and it could only ever be taken by hand. These cover the parts that
decide whether an automatic one can be trusted: that it happens, that it does
not happen twice, that one budget failing does not stop the rest, and that
pruning never touches a snapshot a person asked for.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from igab.config import settings
from igab.repositories.settings_repo import SettingsRepository
from igab.services import budget_snapshot
from igab.services.settings_service import SettingsService
from igab.tasks.snapshot_job import (
    INTERVAL_KEY,
    KEEP_KEY,
    LAST_ERROR_KEY,
    LAST_RUN_KEY,
    run_scheduled_snapshots,
)

from .factories import create_budget, create_user


@pytest.fixture
def snapshot_store(tmp_path, monkeypatch):
    """A scratch BACKUPS_DIR, so the job does not need the real volume."""
    monkeypatch.setattr(settings, "BACKUPS_DIR", str(tmp_path))
    return tmp_path


async def _set(db_session, **pairs):
    service = SettingsService(SettingsRepository(db_session))
    for key, value in pairs.items():
        await service.set(key, value)
    await db_session.commit()


async def _get(db_session, key):
    db_session.expire_all()
    return await SettingsService(SettingsRepository(db_session)).get(key)


def _names(budget_id):
    return [f["name"] for f in budget_snapshot.list_snapshots(budget_id)]


class _NoRollback:
    """The test's session with `rollback` neutered.

    The job takes a session per budget precisely so one failure cannot
    discard another's work; handing it the test's single session collapses
    that isolation, and a real rollback would take the test's own outer
    transaction with it. What the failure test actually asserts — what
    reached disk, and what was recorded — does not depend on the rollback.
    """

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    async def rollback(self):
        return None


def _session_factory(session):
    """The job opens its own sessions; hand it the test's."""
    wrapped = _NoRollback(session)

    class _Ctx:
        async def __aenter__(self):
            return wrapped

        async def __aexit__(self, *exc):
            return False

    return lambda: _Ctx()


async def _run(db_session):
    with patch("igab.db.session.AsyncSessionLocal", _session_factory(db_session)):
        await run_scheduled_snapshots()


class TestItRuns:
    async def test_it_writes_one_scheduled_snapshot_per_budget(self, db_session, snapshot_store):
        user = await create_user(db_session)
        first = await create_budget(db_session, user, "Household")
        second = await create_budget(db_session, user, "Harborstone")
        await db_session.commit()

        await _set(db_session, **{INTERVAL_KEY: "24", KEEP_KEY: "7"})
        await _run(db_session)

        for budget in (first, second):
            names = _names(budget.id)
            assert len(names) == 1, names
            assert budget_snapshot.is_scheduled_snapshot(names[0]), names[0]

    async def test_it_records_when_it_last_ran(self, db_session, snapshot_store):
        user = await create_user(db_session)
        await create_budget(db_session, user, "Household")
        await db_session.commit()
        await _set(db_session, **{INTERVAL_KEY: "24"})

        await _run(db_session)

        assert await _get(db_session, LAST_RUN_KEY)
        # Empty, not absent: "the last run had no failures" is a fact worth
        # stating, and a UI reading a missing key cannot tell the difference
        # between a clean run and one that never happened.
        assert await _get(db_session, LAST_ERROR_KEY) == ""


class TestItDoesNotRunTwice:
    async def test_it_is_a_no_op_inside_the_interval(self, db_session, snapshot_store):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        await db_session.commit()
        await _set(db_session, **{INTERVAL_KEY: "24"})

        await _run(db_session)
        assert len(_names(budget.id)) == 1

        # The scheduler fires hourly; the interval is what decides.
        await _run(db_session)
        assert len(_names(budget.id)) == 1

    async def test_it_runs_again_once_the_interval_has_passed(self, db_session, snapshot_store):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        await db_session.commit()
        long_ago = (datetime.now(tz=UTC) - timedelta(days=3)).isoformat()
        await _set(db_session, **{INTERVAL_KEY: "24", LAST_RUN_KEY: long_ago})

        await _run(db_session)
        assert len(_names(budget.id)) == 1

    async def test_zero_hours_turns_it_off(self, db_session, snapshot_store):
        """The off switch. Retention is never allowed to be zero, so this is
        the only way to say 'do not do this'."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        await db_session.commit()
        await _set(db_session, **{INTERVAL_KEY: "0"})

        await _run(db_session)
        assert _names(budget.id) == []


class TestFailureIsRecorded:
    async def test_one_budget_failing_does_not_stop_the_others(
        self, db_session, snapshot_store, monkeypatch
    ):
        """A backup that has been silently failing for six weeks is worse
        than no backup, because it was believed."""
        user = await create_user(db_session)
        doomed = await create_budget(db_session, user, "Household")
        healthy = await create_budget(db_session, user, "Harborstone")
        await db_session.commit()
        await _set(db_session, **{INTERVAL_KEY: "24"})

        real = budget_snapshot.write_kept_snapshot

        async def flaky(session, budget_id, **kwargs):
            if budget_id == doomed.id:
                raise OSError("No space left on device")
            return await real(session, budget_id, **kwargs)

        monkeypatch.setattr(budget_snapshot, "write_kept_snapshot", flaky)
        await _run(db_session)

        assert _names(doomed.id) == []
        assert len(_names(healthy.id)) == 1
        recorded = await _get(db_session, LAST_ERROR_KEY)
        assert recorded and "No space left" in recorded


def _seed(budget_id, *names):
    """Snapshots from earlier runs, placed directly.

    The filename carries a whole-second stamp, so three runs inside one
    second would write one file three times rather than three files — a
    non-issue on a schedule measured in hours, and an unrunnable test. These
    stand in for the history the job would have built up.
    """
    directory = budget_snapshot.snapshots_dir(budget_id)
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_bytes(b"old")


class TestPruning:
    async def test_it_keeps_only_the_allowance(self, db_session, snapshot_store):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        await db_session.commit()
        _seed(
            budget.id,
            "household-20260901-020000-auto.igab.zip",
            "household-20260902-020000-auto.igab.zip",
            "household-20260903-020000-auto.igab.zip",
        )
        await _set(db_session, **{INTERVAL_KEY: "24", KEEP_KEY: "2"})

        await _run(db_session)

        names = _names(budget.id)
        assert len(names) == 2, names
        # The run's own snapshot is the newest, so the two oldest go.
        assert "household-20260901-020000-auto.igab.zip" not in names
        assert "household-20260902-020000-auto.igab.zip" not in names

    async def test_a_snapshot_someone_asked_for_is_never_pruned(self, db_session, snapshot_store):
        """Theirs, taken before a risky import. Retention counts only the
        automatic ones — see domain/snapshot_retention.py."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user, "Household")
        await db_session.commit()
        mine = "household-20260815-134500.igab.zip"
        _seed(
            budget.id,
            mine,
            "household-20260901-020000-auto.igab.zip",
            "household-20260902-020000-auto.igab.zip",
        )
        await _set(db_session, **{INTERVAL_KEY: "24", KEEP_KEY: "1"})

        await _run(db_session)

        names = _names(budget.id)
        assert mine in names, names
        # Only the run's own automatic snapshot survives the allowance of 1 —
        # and the manual one was never counted toward it.
        assert len([n for n in names if budget_snapshot.is_scheduled_snapshot(n)]) == 1
