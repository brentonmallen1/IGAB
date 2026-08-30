"""Reordering is recorded, shows in Activity, and undoes — LIFO-accurately.

The record carries the complete order before and after (hidden rows
included), never the client's partial list, so walking Activity backwards
lands exactly on the earlier arrangement. Rows created since go to the end
and rows deleted since are skipped, rather than the undo failing.
"""

import pytest
from sqlalchemy import select

from igab.db.models import ChangeLog
from igab.domain.exceptions import UndoConflict
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository
from igab.services.undo_service import UndoService

from .factories import create_budget, create_category, create_category_group


async def _setup(db_session, user):
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Bills")
    cats = []
    for position, name in enumerate(("Rent", "Power", "Water")):
        cat = await create_category(db_session, budget, group, name)
        cat.sort_order = position
        cats.append(cat)
    await db_session.flush()
    return budget, group, cats


async def _reorders(db_session, budget) -> list[ChangeLog]:
    await db_session.flush()
    rows = await db_session.execute(
        select(ChangeLog)
        .where(ChangeLog.budget_id == budget.id, ChangeLog.action == "reorder")
        .order_by(ChangeLog.seq)
    )
    return list(rows.scalars().all())


async def _order(db_session, group) -> list[str]:
    db_session.expunge_all()
    return [c.name for c in await CategoryRepository(db_session).get_by_group(group.id)]


async def _post_order(api_client, budget, group, cats) -> None:
    resp = await api_client.post(
        f"/api/v1/{budget.id}/category-groups/{group.id}/categories/reorder",
        json={"category_ids": [str(c.id) for c in cats]},
    )
    assert resp.status_code == 204, resp.text


async def test_a_reorder_is_recorded_with_the_complete_order(api_client, db_session):
    budget, group, cats = await _setup(db_session, api_client.test_user)
    await _post_order(api_client, budget, group, [cats[2], cats[0], cats[1]])

    (row,) = await _reorders(db_session, budget)
    assert row.entity_type == "category_group"
    assert row.entity_id == group.id
    assert row.before["_order"] == [str(cats[0].id), str(cats[1].id), str(cats[2].id)]
    assert row.after["_order"] == [str(cats[2].id), str(cats[0].id), str(cats[1].id)]


async def test_a_reorder_that_changes_nothing_records_nothing(api_client, db_session):
    budget, group, cats = await _setup(db_session, api_client.test_user)
    await _post_order(api_client, budget, group, cats)
    assert await _reorders(db_session, budget) == []


async def test_undo_restores_the_previous_order(api_client, db_session):
    budget, group, cats = await _setup(db_session, api_client.test_user)
    await _post_order(api_client, budget, group, [cats[2], cats[0], cats[1]])
    (row,) = await _reorders(db_session, budget)

    await UndoService(db_session).undo_change(budget.id, row.id)
    assert await _order(db_session, group) == ["Rent", "Power", "Water"]


async def test_two_reorders_undo_in_reverse_to_the_original(api_client, db_session):
    budget, group, cats = await _setup(db_session, api_client.test_user)
    await _post_order(api_client, budget, group, [cats[2], cats[0], cats[1]])  # Water Rent Power
    await _post_order(api_client, budget, group, [cats[1], cats[2], cats[0]])  # Power Water Rent
    first, second = await _reorders(db_session, budget)
    undo = UndoService(db_session)

    await undo.undo_change(budget.id, second.id)
    assert await _order(db_session, group) == ["Water", "Rent", "Power"]
    await undo.undo_change(budget.id, first.id)
    assert await _order(db_session, group) == ["Rent", "Power", "Water"]


async def test_undo_refuses_when_the_order_changed_since_unless_forced(api_client, db_session):
    budget, group, cats = await _setup(db_session, api_client.test_user)
    await _post_order(api_client, budget, group, [cats[2], cats[0], cats[1]])
    await _post_order(api_client, budget, group, [cats[1], cats[2], cats[0]])
    first, _ = await _reorders(db_session, budget)
    undo = UndoService(db_session)

    with pytest.raises(UndoConflict, match="changed since"):
        await undo.undo_change(budget.id, first.id)
    await undo.undo_change(budget.id, first.id, force=True)
    assert await _order(db_session, group) == ["Rent", "Power", "Water"]


async def test_redo_reapplies_the_order(api_client, db_session):
    budget, group, cats = await _setup(db_session, api_client.test_user)
    await _post_order(api_client, budget, group, [cats[2], cats[0], cats[1]])
    (row,) = await _reorders(db_session, budget)
    undo = UndoService(db_session)

    await undo.undo_change(budget.id, row.id)
    assert await _order(db_session, group) == ["Rent", "Power", "Water"]
    await undo.redo_latest(budget.id)
    assert await _order(db_session, group) == ["Water", "Rent", "Power"]


async def test_a_category_created_after_the_reorder_survives_undo_at_the_end(
    api_client, db_session
):
    budget, group, cats = await _setup(db_session, api_client.test_user)
    await _post_order(api_client, budget, group, [cats[2], cats[0], cats[1]])
    (row,) = await _reorders(db_session, budget)
    resp = await api_client.post(
        f"/api/v1/{budget.id}/categories",
        json={"category_group_id": str(group.id), "name": "Internet"},
    )
    assert resp.status_code == 201

    await UndoService(db_session).undo_change(budget.id, row.id)
    assert await _order(db_session, group) == ["Rent", "Power", "Water", "Internet"]


async def test_a_category_deleted_since_is_skipped_by_undo(api_client, db_session):
    budget, group, cats = await _setup(db_session, api_client.test_user)
    await _post_order(api_client, budget, group, [cats[2], cats[0], cats[1]])
    (row,) = await _reorders(db_session, budget)
    cats[0].is_deleted = True  # Rent, gone
    await db_session.flush()

    await UndoService(db_session).undo_change(budget.id, row.id)
    assert await _order(db_session, group) == ["Power", "Water"]


async def test_a_group_reorder_is_recorded_against_the_budget_and_undoes(api_client, db_session):
    user = api_client.test_user
    budget = await create_budget(db_session, user)
    income = await create_category_group(db_session, budget, "Income", is_system=True)
    bills = await create_category_group(db_session, budget, "Bills")
    wants = await create_category_group(db_session, budget, "Wants")
    income.sort_order, bills.sort_order, wants.sort_order = 0, 1, 2
    await db_session.flush()

    resp = await api_client.post(
        f"/api/v1/{budget.id}/category-groups/reorder",
        json={"group_ids": [str(wants.id), str(bills.id)]},
    )
    assert resp.status_code == 204
    (row,) = await _reorders(db_session, budget)
    assert row.entity_type == "budget"
    assert row.entity_id == budget.id
    # The record holds everyone, the omitted system group included.
    assert row.before["_order"] == [str(income.id), str(bills.id), str(wants.id)]
    assert row.after["_order"] == [str(income.id), str(wants.id), str(bills.id)]

    await UndoService(db_session).undo_change(budget.id, row.id)
    db_session.expunge_all()
    everyone = await CategoryGroupRepository(db_session).get_all(budget.id, include_archived=True)
    assert [g.name for g in everyone] == ["Income", "Bills", "Wants"]
