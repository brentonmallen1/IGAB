"""Ordering the budget's own category groups.

The order is the user's mental model of their money — bills before wants
before savings — so it has to persist, and it has to move as one piece. A
per-group PATCH could half-apply and leave an order nobody chose.
"""

import uuid

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.repositories.category_repo import CategoryGroupRepository

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_user,
)


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
            json={"group_ids": [str(groups[0].id), str(groups[0].id), str(groups[1].id)]},
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
            json={"group_ids": [str(groups[0].id), str(groups[1].id), str(uuid.uuid4())]},
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
        groups[1].is_archived = True  # Wants, holding slot 1
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
        groups[1].is_archived = True
        await db_session.flush()

        repo = CategoryGroupRepository(db_session)
        await repo.reorder(budget.id, [groups[2].id, groups[0].id])
        db_session.expunge_all()
        everyone = [g.name for g in await repo.get_all(budget.id, include_archived=True)]
        assert everyone == ["Savings", "Wants", "Bills"]

    async def test_a_hidden_group_may_still_be_listed(self, db_session):
        """Show-hidden mode sends the full list; that keeps working."""
        budget, groups = await _budget_with_groups(db_session)
        groups[0].is_archived = True
        await db_session.flush()

        repo = CategoryGroupRepository(db_session)
        await repo.reorder(budget.id, [groups[1].id, groups[0].id, groups[2].id])
        db_session.expunge_all()
        everyone = [g.name for g in await repo.get_all(budget.id, include_archived=True)]
        assert everyone == ["Wants", "Bills", "Savings"]

    async def test_a_missing_visible_group_is_still_refused(self, db_session):
        """Omission is a hidden-group privilege; a missing visible group is
        still the stale-client case and fails loudly."""
        budget, groups = await _budget_with_groups(db_session)
        groups[1].is_archived = True
        await db_session.flush()

        with pytest.raises(InvariantViolation, match="visible groups"):
            await CategoryGroupRepository(db_session).reorder(budget.id, [groups[0].id])


class TestCardOnlyGroups:
    """A group holding nothing but card set-aside envelopes is never drawn, so
    the client cannot list it — and until now the server still demanded it.

    The grid dropped card-only groups while `reorder` allowed omitting only
    hidden or system ones, so neither flag was the one the grid was actually
    filtering on.

    It presented as flakiness because it hinges on the grid's **show hidden**
    toggle. "Credit Card Payments" is created hidden (`card_payment.py`), so
    with the toggle off it never reaches the client and reorder works; turn it
    on and the group appears, gets dropped as card-only, and dragging dies. Two
    people on the same build and the same budget saw different behaviour.

    A card-only group that is *visible* — the toggle irrelevant, reorder dead
    either way — is reachable by unhiding the group, which nothing prevents.
    Both shapes are covered below.
    """

    async def _with_card_group(self, db_session, user=None, hidden=False):
        budget, groups = await _budget_with_groups(db_session, user=user)
        cards = await create_category_group(db_session, budget, "Credit Card Payments")
        cards.sort_order = 3
        cards.is_archived = hidden
        visa = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
        envelope = await create_category(db_session, budget, cards, "Sapphire Visa")
        envelope.linked_account_id = visa.id
        await db_session.flush()
        return budget, groups, cards

    async def test_a_visible_card_only_group_may_be_omitted(self, api_client, db_session):
        """The YNAB-import shape: visible, non-system, and drawn by nothing."""
        budget, groups, cards = await self._with_card_group(db_session, user=api_client.test_user)
        assert not cards.is_archived and not cards.is_system

        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups/reorder",
            json={"group_ids": [str(groups[2].id), str(groups[0].id), str(groups[1].id)]},
        )
        assert resp.status_code == 204
        db_session.expunge_all()
        assert await _order(db_session, budget) == [
            "Savings",
            "Bills",
            "Wants",
            "Credit Card Payments",
        ]

    async def test_an_omitted_card_group_keeps_its_slot(self, db_session):
        budget, groups, cards = await self._with_card_group(db_session)
        cards.sort_order = 1
        groups[1].sort_order = 2
        groups[2].sort_order = 3
        await db_session.flush()

        repo = CategoryGroupRepository(db_session)
        await repo.reorder(budget.id, [groups[2].id, groups[1].id, groups[0].id])
        db_session.expunge_all()
        assert await _order(db_session, budget) == [
            "Savings",
            "Credit Card Payments",
            "Wants",
            "Bills",
        ]

    async def test_a_hidden_card_only_group_may_be_omitted_too(self, db_session):
        """The native path's shape. It worked before only because it was
        hidden — for the wrong reason, which is why the import case broke."""
        budget, groups, _cards = await self._with_card_group(db_session, hidden=True)
        repo = CategoryGroupRepository(db_session)
        await repo.reorder(budget.id, [groups[1].id, groups[0].id, groups[2].id])
        db_session.expunge_all()
        assert await _order(db_session, budget) == ["Wants", "Bills", "Savings"]

    async def test_a_group_with_one_ordinary_category_is_still_required(self, db_session):
        """One non-card row and the grid draws the header, so the client can
        and must list it. Omission is not a card-group privilege in general."""
        budget, groups, cards = await self._with_card_group(db_session)
        await create_category(db_session, budget, cards, "Annual Fee")
        await db_session.flush()

        with pytest.raises(InvariantViolation, match="visible groups"):
            await CategoryGroupRepository(db_session).reorder(
                budget.id, [groups[2].id, groups[0].id, groups[1].id]
            )

    async def test_an_empty_group_is_not_card_only(self, db_session):
        """A group the user just made still needs its header to drop into, so
        it is drawn — and therefore still required in a reorder."""
        budget, groups = await _budget_with_groups(db_session)
        fresh = await create_category_group(db_session, budget, "New")
        fresh.sort_order = 3
        await db_session.flush()

        with pytest.raises(InvariantViolation, match="visible groups"):
            await CategoryGroupRepository(db_session).reorder(
                budget.id, [groups[0].id, groups[1].id, groups[2].id]
            )

    async def test_the_listing_serves_the_flag(self, api_client, db_session):
        budget, _groups, _cards = await self._with_card_group(db_session, user=api_client.test_user)
        listed = (
            await api_client.get(f"/api/v1/{budget.id}/category-groups?include_archived=true")
        ).json()
        by_name = {g["name"]: g["is_card_only"] for g in listed}
        assert by_name["Credit Card Payments"] is True
        assert by_name["Bills"] is False
