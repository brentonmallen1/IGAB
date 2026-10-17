"""After a write, a burst of readers rebuilds the snapshot cache once.

A write invalidates the cache, and the browser then refetches several things
at once — the month, the month before it, the dropdown's totals. Each found
the cache invalid and rebuilt the whole budget's rows, all at the same time,
each then waiting on the others' row locks: four refetches took 500 ms where
the same four took 210 ms with the cache valid. `_snapshot_balances` now
takes a per-budget transaction lock before rebuilding and looks again once it
holds it, so the readers behind the first find its rows instead of redoing
them.

This needs real concurrency — separate connections, committed data — so it
cannot run inside the rolled-back `db_session` the rest of the suite uses. It
builds its own budget, commits it, and deletes it again at the end.
"""

import asyncio
from datetime import date
from decimal import Decimal as D

from sqlalchemy import delete, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from igab.db.models import Budget, User
from igab.repositories.snapshot_repo import SnapshotRepository

from .conftest import _url
from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

MONTH = date(2026, 7, 1)
READERS = 4


def _session(engine) -> AsyncSession:
    return AsyncSession(engine, expire_on_commit=False, autoflush=False)


def _budgets(session):
    services = make_services(session)
    services.budgets.snapshot_repo = SnapshotRepository(session)
    return services.budgets


async def test_a_burst_of_readers_rebuilds_once_and_all_see_the_write(test_db):
    engine = create_async_engine(_url(test_db), poolclass=NullPool)
    rebuilds: list[str] = []

    def watch(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("INSERT INTO category_month_snapshots"):
            rebuilds.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", watch)

    async with _session(engine) as s:
        user = await create_user(s)
        budget = await create_budget(s, user)
        checking = await create_account(s, budget, "Checking")
        income = await create_category_group(s, budget, "Income", is_system=True)
        inflow = await create_category(s, budget, income, "Inflow")
        everyday = await create_category_group(s, budget, "Everyday")
        groceries = await create_category(s, budget, everyday, "Groceries")
        await create_transaction(s, budget, checking, "1000.00", MONTH, category=inflow)
        await _budgets(s).set_assignment(budget.id, groceries.id, MONTH, D("300"))
        await s.commit()

    async def read() -> tuple[D, D]:
        async with _session(engine) as s:
            summary = await _budgets(s).get_budget_summary(budget.id, MONTH)
            await s.commit()
        by_cat = {b.category_id: b for b in summary.category_balances}
        return summary.to_be_assigned, by_cat[groceries.id].available

    try:
        first = await asyncio.gather(*(read() for _ in range(READERS)))
        assert first == [(D("700"), D("300"))] * READERS
        assert len(rebuilds) == 1, f"{len(rebuilds)} rebuilds for one invalidation"

        # A committed write invalidates; the next burst rebuilds once more,
        # and every reader in it sees the write.
        async with _session(engine) as s:
            await _budgets(s).set_assignment(budget.id, groceries.id, MONTH, D("450"))
            await s.commit()
        rebuilds.clear()
        second = await asyncio.gather(*(read() for _ in range(READERS)))
        assert second == [(D("550"), D("450"))] * READERS
        assert len(rebuilds) == 1, f"{len(rebuilds)} rebuilds for one invalidation"
    finally:
        async with _session(engine) as s:
            await s.execute(delete(Budget).where(Budget.id == budget.id))
            await s.execute(delete(User).where(User.id == user.id))
            await s.commit()
        await engine.dispose()


async def test_a_writer_reading_its_own_write_rebuilds_inside_its_transaction(test_db):
    """The lock must not let a transaction serve the cache its own write
    invalidated: it still sees its own invalidation after taking the lock."""
    engine = create_async_engine(_url(test_db), poolclass=NullPool)
    async with _session(engine) as s:
        user = await create_user(s)
        budget = await create_budget(s, user)
        everyday = await create_category_group(s, budget, "Everyday")
        groceries = await create_category(s, budget, everyday, "Groceries")
        await s.commit()
    try:
        async with _session(engine) as s:
            budgets = _budgets(s)
            await budgets.get_budget_summary(budget.id, MONTH)  # cache built, valid
            await budgets.set_assignment(budget.id, groceries.id, MONTH, D("80"))
            summary = await budgets.get_budget_summary(budget.id, MONTH)
            by_cat = {b.category_id: b for b in summary.category_balances}
            assert by_cat[groceries.id].assigned == D("80")
            await s.rollback()
    finally:
        async with _session(engine) as s:
            await s.execute(delete(Budget).where(Budget.id == budget.id))
            await s.execute(delete(User).where(User.id == user.id))
            await s.commit()
        await engine.dispose()
