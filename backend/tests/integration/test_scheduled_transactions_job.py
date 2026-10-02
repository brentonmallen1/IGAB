"""The job that posts scheduled transactions: what it runs on, and when it refuses.

`process_due` is tested in test_scheduled_transactions.py. These run the job
around it — the same function the nightly cron and the startup catch-up both
call — with the scheduler's own session handed the test's.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import text

from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
from igab.services.budget_snapshot import migration_history
from igab.services.scheduled_transaction_service import (
    ScheduledTransactionCreate,
    ScheduledTransactionService,
)
from igab.tasks.scheduler import process_due_scheduled_transactions
from igab.utils.clock import today_server_local

from .factories import create_account, create_budget, create_payee, create_user, make_services


def _session_factory(session):
    """The job opens its own session; hand it the test's."""

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    return lambda: _Ctx()


async def _schedule(db_session, *, start, frequency="monthly"):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Harborstone Checking")
    payee = await create_payee(db_session, budget, "Northwind Utilities")
    sched_svc = ScheduledTransactionService(
        ScheduledTransactionRepository(db_session), services.transactions
    )
    sched = await sched_svc.create(
        budget.id,
        ScheduledTransactionCreate(
            account_id=checking.id,
            amount=Decimal("-85.00"),
            frequency=frequency,
            start_date=start,
            payee_id=payee.id,
        ),
    )
    await db_session.flush()
    return services, checking, sched


async def _run_job(db_session, *, today=None):
    with patch("igab.db.session.AsyncSessionLocal", _session_factory(db_session)):
        if today is None:
            await process_due_scheduled_transactions()
        else:
            with patch("igab.utils.clock.today_server_local", return_value=today):
                await process_due_scheduled_transactions()


async def _posted(services, account_id):
    return sorted(r.date for r in await services.transaction_repo.get_for_account(account_id))


async def test_the_job_posts_a_schedule_due_today(db_session):
    """What the startup catch-up and the nightly cron each run: a schedule
    due today posts on the next run, with no setting to turn on first."""
    today = today_server_local()
    services, checking, _ = await _schedule(db_session, start=today)

    await _run_job(db_session)

    assert await _posted(services, checking.id) == [today]


async def test_a_catch_up_after_downtime_posts_every_missed_occurrence_on_its_own_day(db_session):
    """The server was down for three weeks of a weekly bill: the run that
    comes back (the startup one) posts each, dated the day it fell on."""
    today = today_server_local()
    first = today - timedelta(days=14)
    services, checking, sched = await _schedule(db_session, start=first, frequency="weekly")

    await _run_job(db_session)

    assert await _posted(services, checking.id) == [first, first + timedelta(days=7), today]
    refreshed = await ScheduledTransactionRepository(db_session).get(sched.id)
    assert refreshed.next_occurrence_date == today + timedelta(days=7)


async def test_the_job_asks_the_households_clock_not_utc(db_session):
    """The cron fires at 00:05 in TZ; the job then asked for the UTC date, so
    a household west of UTC had tomorrow's bill posted at dinner time. The
    day it posts for is `today_server_local()`'s."""
    households_today = today_server_local() + timedelta(days=1)
    services, checking, _ = await _schedule(db_session, start=households_today)

    await _run_job(db_session, today=households_today - timedelta(days=1))
    assert await _posted(services, checking.id) == []

    await _run_job(db_session, today=households_today)
    assert await _posted(services, checking.id) == [households_today]


async def _stamp_revision(db_session, revision: str) -> None:
    await db_session.execute(text("CREATE TABLE alembic_version (version_num varchar(32))"))
    await db_session.execute(text("INSERT INTO alembic_version VALUES (:r)"), {"r": revision})


async def test_a_database_behind_the_code_posts_nothing(db_session):
    """Code started on a database that has not run the roll-forward migration
    — `just dev-backend` on a dev copy owed one — would post every overdue
    schedule's backlog on its first run. The job waits for the migrations."""
    history = migration_history()
    today = today_server_local()
    services, checking, _ = await _schedule(db_session, start=today - timedelta(days=60))
    await _stamp_revision(db_session, history[-2])

    await _run_job(db_session)

    assert await _posted(services, checking.id) == []


async def test_a_database_at_the_head_posts(db_session):
    history = migration_history()
    today = today_server_local()
    services, checking, _ = await _schedule(db_session, start=today)
    await _stamp_revision(db_session, history[-1])

    await _run_job(db_session)

    assert await _posted(services, checking.id) == [today]
