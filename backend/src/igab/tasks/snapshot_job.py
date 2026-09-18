"""Taking a budget snapshot on a schedule, and pruning the old ones.

Two backup systems already exist and this is neither of them. The db-backup
agent takes a pg_dump of the whole installation on an interval; a budget
snapshot is an app-level zip of ONE budget that can be restored into a
different install, and it could only ever be taken by hand. That left the
portable, per-budget copy — the one worth having before a risky import, and
the only one that survives moving to another machine — as the one nobody had.

It runs in the API process rather than in the agent because a snapshot is
pure SQLAlchemy serialization: no pg_dump, no client binaries, nothing the
API container lacks. The agent exists precisely because the API image has no
postgres client tools, and that reason does not apply here.

Failure policy: one budget's failure never stops the others, and the failure
is RECORDED rather than only logged. A backup that has been silently failing
for six weeks is worse than no backup at all, because it was believed.
"""

import logging
from datetime import UTC, datetime

from igab.domain.snapshot_retention import to_prune

logger = logging.getLogger(__name__)

#: Settings keys. Two the person sets, two the job writes back.
INTERVAL_KEY = "snapshot_interval_hours"
KEEP_KEY = "snapshot_keep_count"
LAST_RUN_KEY = "snapshot_last_auto_at"
LAST_ERROR_KEY = "snapshot_last_auto_error"

DEFAULT_INTERVAL_HOURS = 24
DEFAULT_KEEP = 7


def _as_int(raw: str | None, fallback: int) -> int:
    """A settings value as a number, falling back rather than raising.

    The API validates on write, so a bad value here means the row was edited
    outside the app. Taking the default is the safe reading: it keeps
    snapshots happening, and `to_prune` independently refuses a non-positive
    keep count, so no path through a malformed setting deletes anything.
    """
    try:
        return int(raw) if raw is not None and raw != "" else fallback
    except ValueError:
        return fallback


def _due(last_run: str | None, interval_hours: int, now: datetime) -> bool:
    """Whether enough time has passed. An unreadable or absent stamp is due —
    a schedule that has never run should run."""
    if not last_run:
        return True
    try:
        previous = datetime.fromisoformat(last_run)
    except ValueError:
        return True
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=UTC)
    return (now - previous).total_seconds() >= interval_hours * 3600


async def run_scheduled_snapshots() -> None:
    """One snapshot per budget, then prune this budget's automatic ones."""
    from sqlalchemy import select

    from igab.db.models import Budget
    from igab.db.session import AsyncSessionLocal
    from igab.repositories.settings_repo import SettingsRepository
    from igab.services.budget_snapshot import (
        delete_snapshot,
        list_snapshots,
        write_kept_snapshot,
    )
    from igab.services.settings_service import SettingsService
    from igab.services.update_service import current_version

    async with AsyncSessionLocal() as session:
        settings_service = SettingsService(SettingsRepository(session))
        interval = _as_int(await settings_service.get(INTERVAL_KEY), DEFAULT_INTERVAL_HOURS)
        if interval <= 0:
            return
        now = datetime.now(tz=UTC)
        if not _due(await settings_service.get(LAST_RUN_KEY), interval, now):
            return
        keep = _as_int(await settings_service.get(KEEP_KEY), DEFAULT_KEEP)
        budget_ids = list((await session.execute(select(Budget.id))).scalars().all())

    failures: list[str] = []
    written = 0
    for budget_id in budget_ids:
        # A session per budget: one budget's rollback must not discard
        # another's, and a snapshot reads the whole budget, so holding one
        # transaction open across all of them would be the longest read in
        # the app.
        async with AsyncSessionLocal() as session:
            try:
                path, manifest = await write_kept_snapshot(
                    session, budget_id, app_version=current_version(), scheduled=True
                )
                written += 1
                logger.info("snapshot: wrote %s for %s", path.name, manifest.budget_name)
                for name in to_prune([f["name"] for f in list_snapshots(budget_id)], keep):
                    delete_snapshot(budget_id, name)
                    logger.info("snapshot: pruned %s", name)
            except Exception as exc:
                await session.rollback()
                logger.exception("scheduled snapshot failed for budget %s", budget_id)
                failures.append(f"{budget_id}: {exc}")

    async with AsyncSessionLocal() as session:
        settings_service = SettingsService(SettingsRepository(session))
        # The stamp moves even when every budget failed, deliberately: a
        # schedule that retried every tick after a full disk would write the
        # log full and keep the volume full. The error below is what says the
        # run was not a success.
        await settings_service.set(LAST_RUN_KEY, now.isoformat())
        await settings_service.set(
            LAST_ERROR_KEY,
            "; ".join(failures)[:500] if failures else "",
        )
        await session.commit()

    if failures:
        logger.warning("snapshot: %d of %d budgets failed", len(failures), len(budget_ids))
    elif written:
        logger.info("snapshot: wrote %d scheduled snapshot(s)", written)
