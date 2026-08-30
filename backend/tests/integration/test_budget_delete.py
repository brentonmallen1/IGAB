"""Deleting a budget destroys its full entity graph and nothing else.

The endpoint issues a single DELETE FROM budgets and relies on ON DELETE
CASCADE / SET NULL for everything downstream, so this exercises the whole
foreign-key graph at once.

What it no longer does is *name* the tables. It used to assert cascade against
a hand-maintained list of 14 of the 23 budget-owned tables, plus hand-written
survivor counts (``== 3`` accounts, ``== 8`` transactions) that drifted the
moment the fixture changed. Nine tables could have stopped cascading with this
test still green. The list is now derived from the schema
(``igab.db.budget_scope``), built by ``full_budget`` and counted by
``budget_rows.row_counts``, so a table added next month is covered on the day
it lands rather than the day someone remembers.
"""

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.repositories.budget_filter_repo import BudgetFilterRepository

from .budget_rows import assert_fully_populated, row_counts
from .factories import create_budget, create_category, create_category_group, create_user
from .full_budget import build_full_budget, mark_snapshot_cache_valid


async def test_delete_budget_cascades_full_graph(api_client, db_session):
    owner = api_client.test_user
    doomed = await build_full_budget(db_session, owner)
    survivor = await build_full_budget(db_session, owner)
    # Both, and only once both are built — building the second budget
    # invalidates the first one's cache row. See mark_snapshot_cache_valid.
    await mark_snapshot_cache_valid(db_session, doomed.id)
    await mark_snapshot_cache_valid(db_session, survivor.id)

    before = await row_counts(db_session, doomed.id)
    assert_fully_populated(before)
    survivor_before = await row_counts(db_session, survivor.id)
    assert_fully_populated(survivor_before)

    resp = await api_client.delete(f"/api/v1/budgets/{doomed.id}")
    assert resp.status_code == 204

    survived = {
        name: count for name, count in (await row_counts(db_session, doomed.id)).items() if count
    }
    assert not survived, (
        f"deleting the budget left rows behind: {survived}. Every table in "
        f"the graph must cascade from budgets, directly or through a parent."
    )

    assert await row_counts(db_session, survivor.id) == survivor_before


async def test_filter_rejects_another_budgets_categories(db_session):
    """The route guard authorises the filter, not the ids in its body. Without
    an explicit check a member could attach another budget's category ids to a
    filter they legitimately own, then read those names back out of it."""
    user = await create_user(db_session)
    mine = await create_budget(db_session, user, "Mine")
    theirs = await create_budget(db_session, user, "Theirs")
    their_group = await create_category_group(db_session, theirs, "Everyday")
    their_cat = await create_category(db_session, theirs, their_group, "Groceries")

    repo = BudgetFilterRepository(db_session)
    mine_filter = await repo.create(budget_id=mine.id, name="Bills")

    with pytest.raises(InvariantViolation, match="does not belong"):
        await repo.set_categories(mine_filter.id, [their_cat.id])


async def test_filter_accepts_its_own_budgets_categories(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user, "Mine")
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")

    repo = BudgetFilterRepository(db_session)
    f = await repo.create(budget_id=budget.id, name="Bills")
    await repo.set_categories(f.id, [cat.id])

    loaded = await repo.get_with_categories(f.id)
    assert [s.category_id for s in loaded.category_selections] == [cat.id]
