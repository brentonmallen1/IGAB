"""When a bank connection syncs itself, and syncing all of them at once.

Two gaps this covers. A connection could be scheduled for exactly one time a
day, and `sync_interval_hours` sat on the model and in both schemas without a
single reader — two fields claiming to say when a sync runs, one of them dead.
They are now one list of UTC hours, so "every 4 hours" and "at 07:00 and
19:00" are the same kind of thing to the scheduler.

And "Sync All" reached `connections[0]` only, so a household with two banks
never synced the second one from that button.
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from igab.api.v1.schemas.simplefin import SimpleFINUpdateRequest
from igab.integrations.simplefin.client import SimpleFINFeed
from igab.integrations.simplefin.limits import GLOBAL_DAILY_LIMIT
from igab.services.simplefin_service import SimpleFINService
from igab.tasks.scheduler import process_auto_simplefin_sync

from .factories import (
    create_account,
    create_budget,
    create_simplefin_connection,
    create_user,
    make_services,
)

SF_ACCT = "sf-acct-sched"


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    async def get_feed(self, access_url: str, since=None) -> SimpleFINFeed:
        self.calls += 1
        return SimpleFINFeed(transactions=[])

    async def get_accounts(self, access_url: str) -> list[dict]:
        return []


def _service(services) -> SimpleFINService:
    svc = SimpleFINService(
        session=services.session,
        repo=services.simplefin_repo,
        account_repo=services.account_repo,
        txn_repo=services.transaction_repo,
        txn_service=services.transactions,
        matching_service=services.matching,
    )
    svc.client = FakeClient()
    return svc


PATCH_DECRYPT = patch("igab.services.simplefin_service.decrypt", return_value="https://u:p@x.test")


async def _run_scheduler_at(db_session, hour: int) -> list[tuple]:
    """Run the real hourly job with the clock at `hour`, collecting syncs."""
    synced: list[tuple] = []

    async def fake_sync(self, connection_id, budget_id, **kwargs):
        synced.append((connection_id, budget_id))
        return {"imported": 0, "skipped": 0}

    with (
        patch("igab.db.session.AsyncSessionLocal", _session_factory(db_session)),
        patch.object(SimpleFINService, "sync", fake_sync),
        patch("igab.tasks.scheduler.datetime") as clock,
    ):
        clock.now.return_value = datetime(2026, 8, 28, hour, 0, tzinfo=UTC)
        await process_auto_simplefin_sync()
    return synced


async def _scheduled(db_session, hours: list[int]):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await create_account(db_session, budget, "Checking", simplefin_account_id=SF_ACCT)
    conn = await create_simplefin_connection(db_session, user)
    conn.sync_hours = hours
    await db_session.flush()
    return conn, budget


class TestTheSchedule:
    """The scheduler's whole question is "is this hour in the list?" — asked
    of the real job, at the real clock, not of a restatement of it."""

    @pytest.mark.parametrize(
        "hours,hour_now,fires",
        [
            ([0, 6, 12, 18], 12, True),  # every six hours, and it is one of them
            ([0, 6, 12, 18], 13, False),  # …and one it is not
            ([7, 19], 19, True),  # two times a day, picked by hand
            ([7, 19], 7, True),
            ([7, 19], 18, False),
            ([], 0, False),  # empty means never — including midnight
            ([23], 23, True),  # the ends of the day are not special
            ([0], 0, True),
        ],
    )
    async def test_which_hours_fire(self, db_session, hours: list[int], hour_now: int, fires: bool):
        conn, budget = await _scheduled(db_session, hours)

        synced = await _run_scheduler_at(db_session, hour_now)

        assert synced == ([(conn.id, budget.id)] if fires else [])

    async def test_a_disabled_connection_never_fires(self, db_session):
        conn, _ = await _scheduled(db_session, [9])
        conn.sync_enabled = False
        await db_session.flush()

        assert await _run_scheduler_at(db_session, 9) == []


class TestScheduleValidation:
    """The cap is the connection's own rate limit, not a number invented here."""

    def test_hours_are_sorted_and_deduplicated(self):
        body = SimpleFINUpdateRequest(sync_hours=[19, 7, 7, 0])
        assert body.sync_hours == [0, 7, 19]

    def test_an_empty_list_is_a_valid_schedule_meaning_never(self):
        assert SimpleFINUpdateRequest(sync_hours=[]).sync_hours == []

    def test_omitting_the_field_leaves_the_schedule_alone(self):
        assert SimpleFINUpdateRequest(sync_enabled=True).sync_hours is None

    @pytest.mark.parametrize("bad", [[24], [-1], [0, 24]])
    def test_hours_outside_the_day_are_refused(self, bad: list[int]):
        with pytest.raises(ValidationError, match="between 0 and 23"):
            SimpleFINUpdateRequest(sync_hours=bad)

    def test_more_syncs_than_the_daily_limit_are_refused(self):
        too_many = list(range(GLOBAL_DAILY_LIMIT + 1))
        with pytest.raises(ValidationError, match="daily limit"):
            SimpleFINUpdateRequest(sync_hours=too_many)

    def test_exactly_the_daily_limit_is_allowed(self):
        ok = list(range(GLOBAL_DAILY_LIMIT))
        assert SimpleFINUpdateRequest(sync_hours=ok).sync_hours == ok


class TestSyncAll:
    async def test_every_connection_syncs_not_just_the_first(self, db_session):
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        await create_account(db_session, budget, "Checking", simplefin_account_id=SF_ACCT)
        first = await create_simplefin_connection(db_session, user)
        second = await create_simplefin_connection(db_session, user)
        await db_session.flush()

        svc = _service(services)
        with PATCH_DECRYPT:
            result = await svc.sync_all(user.id, budget.id)

        assert [c["connection_id"] for c in result["connections"]] == [first.id, second.id]

    async def test_one_connection_failing_does_not_stop_the_others(self, db_session):
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        await create_account(db_session, budget, "Checking", simplefin_account_id=SF_ACCT)
        broken = await create_simplefin_connection(db_session, user)
        working = await create_simplefin_connection(db_session, user)
        broken.sync_enabled = False  # reports an error rather than raising
        await db_session.flush()

        svc = _service(services)
        with PATCH_DECRYPT:
            result = await svc.sync_all(user.id, budget.id)

        outcomes = {c["connection_id"]: c for c in result["connections"]}
        assert outcomes[broken.id]["error"] is not None
        assert outcomes[working.id]["error"] is None, "the second bank still ran"

    async def test_another_users_connections_are_not_touched(self, db_session):
        services = make_services(db_session)
        user = await create_user(db_session)
        stranger = await create_user(db_session)
        budget = await create_budget(db_session, user)
        await create_account(db_session, budget, "Checking", simplefin_account_id=SF_ACCT)
        mine = await create_simplefin_connection(db_session, user)
        await create_simplefin_connection(db_session, stranger)
        await db_session.flush()

        svc = _service(services)
        with PATCH_DECRYPT:
            result = await svc.sync_all(user.id, budget.id)

        assert [c["connection_id"] for c in result["connections"]] == [mine.id]


def _session_factory(session):
    """The scheduler opens its own session; hand it the test's."""

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    def factory():
        return _Ctx()

    return factory
