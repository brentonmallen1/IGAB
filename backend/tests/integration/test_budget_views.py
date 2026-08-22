"""Views: alternate arrangements of the same categories.

derkus's ask: "i want the concept of views to be completely different ways to
look at the categories. like being able to have categories that move to
different groups based on the view." His real groups are types of expense;
he wants to read the same budget as need/want/save without cloning it.

The rules that matter here:
  - a view never touches the default arrangement in category_groups;
  - a category with no placement is not lost — the client shows it under
    Unassigned, so adding a category later can't silently drop it from a view;
  - deleting a group leaves its categories in the view, not out of it;
  - ids in a request body are checked against the view's own budget.
"""

import uuid

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.repositories.budget_view_repo import BudgetViewRepository

from .factories import (
    create_budget,
    create_category,
    create_category_group,
    create_user,
)


async def _budget_with_categories(db_session, owner, names=("Rent", "Dining", "Roth")):
    budget = await create_budget(db_session, owner)
    group = await create_category_group(db_session, budget, "Everyday")
    cats = [await create_category(db_session, budget, group, n) for n in names]
    return budget, cats


class TestViewCrud:
    async def test_create_with_groups(self, api_client, db_session):
        budget, _ = await _budget_with_categories(db_session, api_client.test_user)

        resp = await api_client.post(
            f"/api/v1/{budget.id}/views",
            json={"name": "Need / Want / Save", "groups": ["Need", "Want", "Save"]},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Need / Want / Save"
        assert [g["name"] for g in body["groups"]] == ["Need", "Want", "Save"]
        assert body["placements"] == []

    async def test_list_and_delete(self, api_client, db_session):
        budget, _ = await _budget_with_categories(db_session, api_client.test_user)
        created = (
            await api_client.post(f"/api/v1/{budget.id}/views", json={"name": "Lens"})
        ).json()

        listed = (await api_client.get(f"/api/v1/{budget.id}/views")).json()
        assert [v["id"] for v in listed] == [created["id"]]

        assert (await api_client.delete(f"/api/v1/views/{created['id']}")).status_code == 204
        assert (await api_client.get(f"/api/v1/{budget.id}/views")).json() == []

    async def test_duplicate_name_rejected(self, api_client, db_session):
        budget, _ = await _budget_with_categories(db_session, api_client.test_user)
        await api_client.post(f"/api/v1/{budget.id}/views", json={"name": "Lens"})
        resp = await api_client.post(f"/api/v1/{budget.id}/views", json={"name": "Lens"})
        assert resp.status_code == 409
        assert "already" in resp.json()["detail"].lower()


class TestPlacements:
    async def test_categories_move_to_view_groups(self, api_client, db_session):
        """The whole point: the same categories, arranged differently."""
        budget, cats = await _budget_with_categories(db_session, api_client.test_user)
        view = (
            await api_client.post(
                f"/api/v1/{budget.id}/views",
                json={"name": "NWS", "groups": ["Need", "Save"]},
            )
        ).json()
        need, save = view["groups"][0]["id"], view["groups"][1]["id"]

        resp = await api_client.patch(
            f"/api/v1/views/{view['id']}",
            json={
                "placements": [
                    {"category_id": str(cats[0].id), "group_id": need, "sort_order": 0},
                    {"category_id": str(cats[2].id), "group_id": save, "sort_order": 1},
                ]
            },
        )
        assert resp.status_code == 200
        placed = {p["category_id"]: p["group_id"] for p in resp.json()["placements"]}
        assert placed[str(cats[0].id)] == need
        assert placed[str(cats[2].id)] == save
        # The unplaced one is simply absent — the client renders it Unassigned.
        assert str(cats[1].id) not in placed

    async def test_hidden_placement_round_trips(self, api_client, db_session):
        budget, cats = await _budget_with_categories(db_session, api_client.test_user)
        view = (
            await api_client.post(f"/api/v1/{budget.id}/views", json={"name": "NWS"})
        ).json()

        resp = await api_client.patch(
            f"/api/v1/views/{view['id']}",
            json={"placements": [{"category_id": str(cats[0].id), "is_hidden": True}]},
        )
        assert resp.json()["placements"][0]["is_hidden"] is True

    async def test_resaving_groups_keeps_placements(self, db_session):
        """Groups are matched by name on save. Rebuilding them by identity
        would empty every group each time the user pressed Save."""
        user = await create_user(db_session)
        budget, cats = await _budget_with_categories(db_session, user)
        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=budget.id, name="NWS")
        groups = await repo.set_groups(view.id, ["Need", "Want"])
        await repo.set_placements(
            view.id, [{"category_id": cats[0].id, "group_id": groups[0].id}]
        )

        await repo.set_groups(view.id, ["Need", "Want", "Save"])
        loaded = await repo.get_full(view.id)
        assert [p.group_id for p in loaded.placements] == [groups[0].id]

    async def test_deleting_a_group_keeps_its_categories_in_the_view(self, db_session):
        """SET NULL, not CASCADE. A category must fall back to Unassigned
        rather than vanishing from a view the user did not edit."""
        user = await create_user(db_session)
        budget, cats = await _budget_with_categories(db_session, user)
        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=budget.id, name="NWS")
        groups = await repo.set_groups(view.id, ["Need", "Want"])
        await repo.set_placements(
            view.id, [{"category_id": cats[0].id, "group_id": groups[0].id}]
        )

        await repo.set_groups(view.id, ["Want"])
        # The FK nulls the placement's group_id in the database; the identity
        # map still holds the old value, so read it back detached.
        db_session.expunge_all()
        loaded = await repo.get_full(view.id)
        assert len(loaded.placements) == 1, "the category stayed in the view"
        assert loaded.placements[0].group_id is None, "and fell back to Unassigned"


class TestOwnership:
    async def test_rejects_another_budgets_category(self, db_session):
        user = await create_user(db_session)
        mine, _ = await _budget_with_categories(db_session, user)
        theirs, their_cats = await _budget_with_categories(db_session, user)

        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=mine.id, name="NWS")
        with pytest.raises(InvariantViolation, match="does not belong"):
            await repo.set_placements(view.id, [{"category_id": their_cats[0].id}])

    async def test_rejects_another_views_group(self, db_session):
        user = await create_user(db_session)
        budget, cats = await _budget_with_categories(db_session, user)
        repo = BudgetViewRepository(db_session)
        a = await repo.create(budget_id=budget.id, name="A")
        b = await repo.create(budget_id=budget.id, name="B")
        b_groups = await repo.set_groups(b.id, ["Elsewhere"])

        with pytest.raises(InvariantViolation, match="does not belong to this view"):
            await repo.set_placements(
                a.id, [{"category_id": cats[0].id, "group_id": b_groups[0].id}]
            )

    async def test_another_users_view_is_not_reachable(self, api_client, db_session):
        other = await create_user(db_session)
        budget, _ = await _budget_with_categories(db_session, other)
        repo = BudgetViewRepository(db_session)
        view = await repo.create(budget_id=budget.id, name="Theirs")

        resp = await api_client.get(f"/api/v1/views/{view.id}")
        assert resp.status_code in (403, 404)

    async def test_unknown_view_is_404(self, api_client):
        resp = await api_client.get(f"/api/v1/views/{uuid.uuid4()}")
        assert resp.status_code in (403, 404)


class TestIsolationFromDefaultArrangement:
    async def test_a_view_does_not_touch_category_groups(self, api_client, db_session):
        from sqlalchemy import select

        from igab.db.models import Category

        budget, cats = await _budget_with_categories(db_session, api_client.test_user)
        before = {
            c.id: c.category_group_id
            for c in (
                await db_session.execute(select(Category).where(Category.budget_id == budget.id))
            ).scalars()
        }

        view = (
            await api_client.post(
                f"/api/v1/{budget.id}/views", json={"name": "NWS", "groups": ["Need"]}
            )
        ).json()
        await api_client.patch(
            f"/api/v1/views/{view['id']}",
            json={
                "placements": [
                    {"category_id": str(c.id), "group_id": view["groups"][0]["id"]}
                    for c in cats
                ]
            },
        )

        db_session.expunge_all()
        after = {
            c.id: c.category_group_id
            for c in (
                await db_session.execute(select(Category).where(Category.budget_id == budget.id))
            ).scalars()
        }
        assert before == after, "a view must never edit the default arrangement"
