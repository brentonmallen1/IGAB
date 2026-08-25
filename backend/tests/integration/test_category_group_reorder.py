"""Ordering the budget's own category groups.

The order is the user's mental model of their money — bills before wants
before savings — so it has to persist, and it has to move as one piece. A
per-group PATCH could half-apply and leave an order nobody chose.
"""

import uuid

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.repositories.category_repo import CategoryGroupRepository

from .factories import create_budget, create_category_group, create_user


async def _budget_with_groups(db_session, names=("Bills", "Wants", "Savings"), user=None):
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    groups = []
    for position, name in enumerate(names):
        group = await create_category_group(db_session, budget, name)
        # The factory leaves sort_order at 0, where listings fall back to
        # alphabetical. Start from a deliberate order so a reorder is visible
        # as a reorder rather than as a change of tiebreak.
        group.sort_order = position
        groups.append(group)
    await db_session.flush()
    return budget, groups


async def _order(db_session, budget) -> list[str]:
    return [g.name for g in await CategoryGroupRepository(db_session).get_all(budget.id)]


class TestReorder:
    async def test_the_new_order_is_what_listings_return(self, api_client, db_session):
        budget, groups = await _budget_with_groups(db_session, user=api_client.test_user)
        assert await _order(db_session, budget) == ["Bills", "Wants", "Savings"]

        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups/reorder",
            json={"group_ids": [str(groups[2].id), str(groups[0].id), str(groups[1].id)]},
        )
        assert resp.status_code == 204
        db_session.expunge_all()
        assert await _order(db_session, budget) == ["Savings", "Bills", "Wants"]

    async def test_it_survives_a_reload(self, api_client, db_session):
        budget, groups = await _budget_with_groups(db_session, user=api_client.test_user)
        await api_client.post(
            f"/api/v1/{budget.id}/category-groups/reorder",
            json={"group_ids": [str(groups[1].id), str(groups[2].id), str(groups[0].id)]},
        )
        db_session.expunge_all()
        listed = (await api_client.get(f"/api/v1/{budget.id}/category-groups")).json()
        assert [g["name"] for g in listed] == ["Wants", "Savings", "Bills"]
        assert [g["sort_order"] for g in listed] == [0, 1, 2]

    async def test_a_partial_list_is_refused(self, api_client, db_session):
        """A stale client — a group added in another tab — must not be able to
        shuffle rows it never showed the user."""
        budget, groups = await _budget_with_groups(db_session, user=api_client.test_user)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups/reorder",
            json={"group_ids": [str(groups[1].id), str(groups[0].id)]},
        )
        assert resp.status_code == 400
        db_session.expunge_all()
        assert await _order(db_session, budget) == ["Bills", "Wants", "Savings"]

    async def test_a_duplicated_id_is_refused(self, api_client, db_session):
        budget, groups = await _budget_with_groups(db_session, user=api_client.test_user)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups/reorder",
            json={
                "group_ids": [str(groups[0].id), str(groups[0].id), str(groups[1].id)]
            },
        )
        assert resp.status_code == 400

    async def test_another_budgets_group_is_refused(self, db_session):
        budget, groups = await _budget_with_groups(db_session)
        other_budget, other_groups = await _budget_with_groups(db_session, ("Theirs",))

        repo = CategoryGroupRepository(db_session)
        with pytest.raises(InvariantViolation, match="does not have"):
            await repo.reorder(
                budget.id,
                [str(groups[0].id), str(groups[1].id), other_groups[0].id],
            )

    async def test_an_unknown_id_is_refused(self, api_client, db_session):
        budget, groups = await _budget_with_groups(db_session, user=api_client.test_user)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups/reorder",
            json={
                "group_ids": [str(groups[0].id), str(groups[1].id), str(uuid.uuid4())]
            },
        )
        assert resp.status_code == 400


class TestHiddenGroups:
    """The budget page drags against the list it shows, and by default that
    list excludes hidden groups — so omitting them must be legal, or any
    budget that has ever hidden a group loses reordering entirely. Found in
    review: the server demanded completeness the client structurally could
    not send, and every drag came back 400."""

    async def test_reorder_succeeds_with_a_hidden_group_omitted(self, api_client, db_session):
        budget, groups = await _budget_with_groups(db_session, user=api_client.test_user)
        groups[1].is_hidden = True  # Wants, holding slot 1
        await db_session.flush()

        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups/reorder",
            json={"group_ids": [str(groups[2].id), str(groups[0].id)]},
        )
        assert resp.status_code == 204
        db_session.expunge_all()
        assert await _order(db_session, budget) == ["Savings", "Bills"]

    async def test_an_omitted_hidden_group_keeps_its_slot(self, db_session):
        """Re-showing the group later must find it where the user left it,
        not dumped at the end."""
        budget, groups = await _budget_with_groups(db_session)
        groups[1].is_hidden = True
        await db_session.flush()

        repo = CategoryGroupRepository(db_session)
        await repo.reorder(budget.id, [groups[2].id, groups[0].id])
        db_session.expunge_all()
        everyone = [g.name for g in await repo.get_all(budget.id, include_hidden=True)]
        assert everyone == ["Savings", "Wants", "Bills"]

    async def test_a_hidden_group_may_still_be_listed(self, db_session):
        """Show-hidden mode sends the full list; that keeps working."""
        budget, groups = await _budget_with_groups(db_session)
        groups[0].is_hidden = True
        await db_session.flush()

        repo = CategoryGroupRepository(db_session)
        await repo.reorder(budget.id, [groups[1].id, groups[0].id, groups[2].id])
        db_session.expunge_all()
        everyone = [g.name for g in await repo.get_all(budget.id, include_hidden=True)]
        assert everyone == ["Wants", "Bills", "Savings"]

    async def test_a_missing_visible_group_is_still_refused(self, db_session):
        """Omission is a hidden-group privilege; a missing visible group is
        still the stale-client case and fails loudly."""
        budget, groups = await _budget_with_groups(db_session)
        groups[1].is_hidden = True
        await db_session.flush()

        with pytest.raises(InvariantViolation, match="visible groups"):
            await CategoryGroupRepository(db_session).reorder(budget.id, [groups[0].id])
