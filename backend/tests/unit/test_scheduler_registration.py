"""How the scheduled-transactions job is registered.

Every schedule posts itself on its date, so a night the server missed is a
night of bills owed. The jobstore is in memory and forgets a missed firing on
restart; the startup run is what catches up, and the cron's coalesce and grace
keep a late or bunched firing from being dropped or run twice.
"""

from unittest.mock import patch

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from igab.tasks import scheduler as scheduler_module
from igab.tasks.scheduler import (
    SCHEDULED_TRANSACTIONS_JOB,
    SCHEDULED_TRANSACTIONS_STARTUP_JOB,
    process_due_scheduled_transactions,
    start_scheduler,
)


def _registered() -> dict:
    fresh = AsyncIOScheduler()
    with (
        patch.object(scheduler_module, "scheduler", fresh),
        patch.object(fresh, "start"),
    ):
        start_scheduler()
    return {job.id: job for job in fresh.get_jobs()}


def test_the_nightly_run_coalesces_and_tolerates_an_hour_late():
    job = _registered()[SCHEDULED_TRANSACTIONS_JOB]
    assert job.func is process_due_scheduled_transactions
    assert isinstance(job.trigger, CronTrigger)
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert (fields["hour"], fields["minute"]) == ("0", "5")
    assert job.coalesce is True
    assert job.misfire_grace_time == 3600


def test_startup_runs_the_same_job_once():
    job = _registered()[SCHEDULED_TRANSACTIONS_STARTUP_JOB]
    assert job.func is process_due_scheduled_transactions
    assert isinstance(job.trigger, DateTrigger), "one shot, not recurring"
