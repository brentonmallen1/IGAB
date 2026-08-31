"""Ordering the categories inside a group, and everything the order rests on.

The category order is the shape of the budget as the user reads it. It has to
persist, move as one piece, come back the same on every read, and — because
the grid buckets by group before it looks at positions — a group must carry
its categories with it when *it* moves.
"""

import uuid

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository

from .factories import create_budget, create_category, create_category_group, create_user


async def _group_with_categories(
    db_session, names=("Rent", "Power", "Water"), user=None, budget=None, group_name="Bills"
):
    user = user or await create_user(db_session)
    budget = budget or await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, group_name)
    cats = []
    for position, name in enumerate(names):
        cat = await create_category(db_session, budget, group, name)
        # The factory leaves sort_order at 0, where listings fall back to
        # alphabetical. Start from a deliberate order so a reorder is visible
        # as a reorder rather than as a change of tiebreak.
        cat.sort_order = position
        cats.append(cat)
    await db_session.flush()
    return budget, group, cats


async def _order(db_session, group) -> list[str]:
    return [c.name for c in await CategoryRepository(db_session).get_by_group(group.id)]


def _url(budget, group) -> str:
    return f"/api/v1/{budget.id}/category-groups/{group.id}/categories/reorder"


class TestReorder:
    async def test_the_new_order_is_what_listings_return(self, api_client, db_session):
        budget, group, cats = await _group_with_categories(db_session, user=api_client.test_user)
        assert await _order(db_session, group) == ["Rent", "Power", "Water"]

        resp = await api_client.post(
            _url(budget, group),
            json={"category_ids": [str(cats[2].id), str(cats[0].id), str(cats[1].id)]},
        )
        assert resp.status_code == 204
        db_session.expunge_all()
        assert await _order(db_session, group) == ["Water", "Rent", "Power"]

    async def test_it_survives_a_reload(self, api_client, db_session):
        budget, group, cats = await _group_with_categories(db_session, user=api_client.test_user)
        await api_client.post(
            _url(budget, group),
            json={"category_ids": [str(cats[1].id), str(cats[2].id), str(cats[0].id)]},
        )
        db_session.expunge_all()
        listed = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        assert [c["name"] for c in listed] == ["Power", "Water", "Rent"]
        assert [c["sort_order"] for c in listed] == [0, 1, 2]

    async def test_a_partial_list_is_refused(self, api_client, db_session):
        """A stale client — a category added in another tab — must not be able
        to shuffle rows it never showed the user."""
        budget, group, cats = await _group_with_categories(db_session, user=api_client.test_user)
        resp = await api_client.post(
            _url(budget, group), json={"category_ids": [str(cats[1].id), str(cats[0].id)]}
        )
        assert resp.status_code == 400
        db_session.expunge_all()
        assert await _order(db_session, group) == ["Rent", "Power", "Water"]

    async def test_a_duplicated_id_is_refused(self, api_client, db_session):
        budget, group, cats = await _group_with_categories(db_session, user=api_client.test_user)
        resp = await api_client.post(
            _url(budget, group),
            json={"category_ids": [str(cats[0].id), str(cats[0].id), str(cats[1].id)]},
        )
        assert resp.status_code == 400

    async def test_an_unknown_id_is_refused(self, api_client, db_session):
        budget, group, cats = await _group_with_categories(db_session, user=api_client.test_user)
        resp = await api_client.post(
            _url(budget, group),
            json={
                "category_ids": [
                    str(cats[0].id),
                    str(cats[1].id),
                    str(cats[2].id),
                    str(uuid.uuid4()),
                ]
            },
        )
        assert resp.status_code == 400

    async def test_another_groups_category_is_refused(self, db_session):
        budget, group, cats = await _group_with_categories(db_session)
        _, other_group, other_cats = await _group_with_categories(
            db_session, ("Fun",), budget=budget, group_name="Wants"
        )
        with pytest.raises(InvariantViolation, match="does not have"):
            await CategoryRepository(db_session).reorder(
                group.id, [cats[0].id, cats[1].id, cats[2].id, other_cats[0].id]
            )

    async def test_another_budgets_group_is_refused(self, api_client, db_session):
        budget, _, _ = await _group_with_categories(db_session, user=api_client.test_user)
        _, their_group, their_cats = await _group_with_categories(db_session, ("Theirs",))
        resp = await api_client.post(
            _url(budget, their_group), json={"category_ids": [str(their_cats[0].id)]}
        )
        assert resp.status_code == 400


class TestHiddenCategories:
    """The grid drags against the list it shows, which by default excludes
    hidden categories — so omitting them must be legal, and an omitted one
    keeps its slot, exactly as hidden groups do."""

    async def test_reorder_succeeds_with_a_hidden_category_omitted(self, api_client, db_session):
        budget, group, cats = await _group_with_categories(db_session, user=api_client.test_user)
        cats[1].is_archived = True  # Power, holding slot 1
        await db_session.flush()

        resp = await api_client.post(
            _url(budget, group), json={"category_ids": [str(cats[2].id), str(cats[0].id)]}
        )
        assert resp.status_code == 204
        db_session.expunge_all()
        assert await _order(db_session, group) == ["Water", "Power", "Rent"]

    async def test_a_missing_visible_category_is_still_refused(self, db_session):
        budget, group, cats = await _group_with_categories(db_session)
        cats[1].is_archived = True
        await db_session.flush()
        with pytest.raises(InvariantViolation, match="visible categories"):
            await CategoryRepository(db_session).reorder(group.id, [cats[0].id])


class TestGroupsCarryTheirCategories:
    async def test_reordering_groups_leaves_every_category_where_it_was(
        self, api_client, db_session
    ):
        """The regression the feature request named: moving a group must move
        its categories with it — and nothing else about them."""
        budget, bills, bill_cats = await _group_with_categories(
            db_session, user=api_client.test_user
        )
        _, wants, want_cats = await _group_with_categories(
            db_session, ("Games", "Dining"), budget=budget, group_name="Wants"
        )
        bills.sort_order, wants.sort_order = 0, 1
        await db_session.flush()

        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups/reorder",
            json={"group_ids": [str(wants.id), str(bills.id)]},
        )
        assert resp.status_code == 204
        db_session.expunge_all()

        groups = await CategoryGroupRepository(db_session).get_all(budget.id)
        assert [g.name for g in groups] == ["Wants", "Bills"]
        assert await _order(db_session, bills) == ["Rent", "Power", "Water"]
        assert await _order(db_session, wants) == ["Games", "Dining"]
        listed = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        by_id = {c["id"]: c for c in listed}
        for cat in [*bill_cats, *want_cats]:
            assert by_id[str(cat.id)]["category_group_id"] == str(cat.category_group_id)


class TestDeterminism:
    async def test_categories_sharing_a_position_list_alphabetically_every_time(
        self, api_client, db_session
    ):
        """Every category a YNAB import ever created shared position 0, and the
        listing had no tiebreak — so the grid reshuffled on every refetch.
        Name breaks the tie now, on every read."""
        user = api_client.test_user
        budget = await create_budget(db_session, user)
        group = await create_category_group(db_session, budget, "Bills")
        for name in ("Water", "Rent", "Power"):
            cat = await create_category(db_session, budget, group, name)
            cat.sort_order = 0
        await db_session.flush()

        seen = set()
        for _ in range(3):
            listed = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
            seen.add(tuple(c["name"] for c in listed))
        assert seen == {("Power", "Rent", "Water")}


class TestNewRowsGoLast:
    async def test_a_new_category_lands_after_the_last_in_its_group(self, api_client, db_session):
        budget, group, _ = await _group_with_categories(db_session, user=api_client.test_user)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/categories",
            json={"category_group_id": str(group.id), "name": "Internet"},
        )
        assert resp.status_code == 201
        assert resp.json()["sort_order"] == 3
        db_session.expunge_all()
        assert await _order(db_session, group) == ["Rent", "Power", "Water", "Internet"]

    async def test_a_new_group_lands_after_the_last(self, api_client, db_session):
        budget, group, _ = await _group_with_categories(db_session, user=api_client.test_user)
        group.sort_order = 4
        await db_session.flush()
        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups", json={"name": "Savings"}
        )
        assert resp.status_code == 201
        assert resp.json()["sort_order"] == 5

    async def test_an_explicit_position_is_kept(self, api_client, db_session):
        budget, group, _ = await _group_with_categories(db_session, user=api_client.test_user)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/categories",
            json={"category_group_id": str(group.id), "name": "Internet", "sort_order": 0},
        )
        assert resp.json()["sort_order"] == 0

    async def test_a_category_moved_to_another_group_is_appended_there(
        self, api_client, db_session
    ):
        budget, bills, bill_cats = await _group_with_categories(
            db_session, user=api_client.test_user
        )
        _, wants, _ = await _group_with_categories(
            db_session, ("Games", "Dining"), budget=budget, group_name="Wants"
        )
        resp = await api_client.patch(
            f"/api/v1/categories/{bill_cats[0].id}", json={"category_group_id": str(wants.id)}
        )
        assert resp.status_code == 200
        assert resp.json()["sort_order"] == 2
        db_session.expunge_all()
        assert await _order(db_session, wants) == ["Games", "Dining", "Rent"]
        assert await _order(db_session, bills) == ["Power", "Water"]

    async def test_a_category_cannot_be_moved_to_another_budgets_group(
        self, api_client, db_session
    ):
        budget, _, bill_cats = await _group_with_categories(db_session, user=api_client.test_user)
        _, their_group, _ = await _group_with_categories(db_session, ("Theirs",))
        resp = await api_client.patch(
            f"/api/v1/categories/{bill_cats[0].id}", json={"category_group_id": str(their_group.id)}
        )
        assert resp.status_code == 400


class TestSystemGroupsMayBeOmitted:
    async def test_a_group_reorder_may_leave_the_income_group_out(self, api_client, db_session):
        """The grid does not draw the Income group, so it cannot list it. The
        old completeness check would have refused every reorder."""
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
        db_session.expunge_all()
        everyone = await CategoryGroupRepository(db_session).get_all(
            budget.id, include_archived=True
        )
        assert [g.name for g in everyone] == ["Income", "Wants", "Bills"]
