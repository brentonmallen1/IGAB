"""Which categories a picker may offer, decided once and served.

Six client components each spelled their own predicate, and the two rules they
were conflating differ on system groups: money must not be *assigned* into the
Income group, but income rows must be *filed* into it. A single flag would have
broken one of the two.

These are the served-field checklist from test_offbudget_categories.py, applied
to `is_assignable` and `is_categorizable`.
"""

import uuid
from decimal import Decimal

import pytest

from igab.api.v1.schemas.category import CategoryResponse
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_user,
    make_services,
)


async def _budget(db_session, user=None):
    user = user or await create_user(db_session)
    return await create_budget(db_session, user)


async def _system_group(db_session, budget, name="Income"):
    group = await create_category_group(db_session, budget, name)
    await CategoryGroupRepository(db_session).update(group.id, is_system=True)
    return group


class TestTheTwoRulesDifferOnSystemGroups:
    async def test_income_can_be_filed_but_not_assigned_into(self, db_session):
        budget = await _budget(db_session)
        group = await _system_group(db_session, budget)
        category = await create_category(db_session, budget, group, "Paycheque")

        loaded = await CategoryRepository(db_session).get(category.id)

        assert loaded.is_categorizable is True, "income has to have somewhere to go"
        assert loaded.is_assignable is False, "money is not budgeted into Income"

    async def test_an_ordinary_category_is_both(self, db_session):
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Everyday")
        category = await create_category(db_session, budget, group, "Groceries")

        loaded = await CategoryRepository(db_session).get(category.id)

        assert loaded.is_assignable is True
        assert loaded.is_categorizable is True


class TestWhatEachRuleExcludes:
    async def test_a_hidden_category_is_neither(self, db_session):
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Everyday")
        category = await create_category(db_session, budget, group, "Old")
        await CategoryRepository(db_session).update(category.id, is_hidden=True)

        loaded = await CategoryRepository(db_session).get(category.id)

        assert loaded.is_assignable is False
        assert loaded.is_categorizable is False

    async def test_a_category_in_a_hidden_group_is_neither(self, db_session):
        # The leak: CategoryRepository.get_all filters the category's is_hidden
        # but not the group's, while CategoryGroupRepository.get_all filters the
        # group's. So these arrived at the client without their group.
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Archive")
        await CategoryGroupRepository(db_session).update(group.id, is_hidden=True)
        category = await create_category(db_session, budget, group, "Stale")

        loaded = await CategoryRepository(db_session).get(category.id)

        assert loaded.is_assignable is False
        assert loaded.is_categorizable is False

    async def test_a_linked_payment_category_may_be_assigned_but_not_filed(self, db_session):
        # A credit-card payment category holds budgeted money; its activity is
        # maintained by the transfer, not by filing a row into it.
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Credit Cards")
        category = await create_category(db_session, budget, group, "Visa")
        account = await create_account(db_session, budget, "Visa", account_type="credit_card")
        await CategoryRepository(db_session).update(category.id, linked_account_id=account.id)

        loaded = await CategoryRepository(db_session).get(category.id)

        assert loaded.is_assignable is True
        assert loaded.is_categorizable is False


class TestEveryPathCarriesTheFlags:
    async def test_get_all_carries_them(self, db_session):
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Everyday")
        await create_category(db_session, budget, group, "Groceries")

        for category in await CategoryRepository(db_session).get_all(budget.id):
            assert category.is_assignable is not None
            assert category.is_categorizable is not None

    async def test_every_mutating_endpoint_returns_a_serializable_row(
        self, db_session, api_client
    ):
        """The check that matters: the endpoints build their response from
        get_with_tags, not from get, and that method had to learn the
        expressions too. The fields are required, so a path that drops one
        500s rather than reporting every category as ineligible."""
        budget = await _budget(db_session, api_client.test_user)
        group = await create_category_group(db_session, budget, "Everyday")

        resp = await api_client.post(
            f"/api/v1/{budget.id}/categories",
            json={"category_group_id": str(group.id), "name": "Fresh"},
        )
        assert resp.status_code in (200, 201), resp.text
        created = resp.json()
        assert created["is_assignable"] is True
        assert created["is_categorizable"] is True

        resp = await api_client.patch(
            f"/api/v1/categories/{created['id']}", json={"name": "Renamed"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_assignable"] is True

        resp = await api_client.get(f"/api/v1/{budget.id}/categories")
        assert resp.status_code == 200, resp.text
        assert all("is_assignable" in c for c in resp.json())

    async def test_get_with_tags_carries_them(self, db_session):
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Everyday")
        category = await create_category(db_session, budget, group, "Groceries")

        loaded = await CategoryRepository(db_session).get_with_tags(category.id)

        CategoryResponse.model_validate(loaded)
        assert loaded.is_assignable is True

    async def test_the_flag_follows_a_group_becoming_system(self, db_session):
        # The reason this cannot be a column: the answer changes without the
        # category row being touched.
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Everyday")
        category = await create_category(db_session, budget, group, "Groceries")
        repo = CategoryRepository(db_session)

        assert (await repo.get(category.id)).is_assignable is True

        await CategoryGroupRepository(db_session).update(group.id, is_system=True)

        assert (await repo.get(category.id)).is_assignable is False


class TestTheServedFlagIsTheOnlyRule:
    async def test_the_assign_endpoint_acts_on_exactly_the_assignable_set(self, db_session):
        """What a picker offers and what Fill/Assign touches must be one set."""
        budget = await _budget(db_session)
        services = make_services(db_session)
        everyday = await create_category_group(db_session, budget, "Everyday")
        income = await _system_group(db_session, budget)
        hidden_group = await create_category_group(db_session, budget, "Archive")
        await CategoryGroupRepository(db_session).update(hidden_group.id, is_hidden=True)

        offered = await create_category(db_session, budget, everyday, "Groceries")
        await create_category(db_session, budget, income, "Paycheque")
        await create_category(db_session, budget, hidden_group, "Stale")

        categories = await CategoryRepository(db_session).get_all(budget.id)
        assignable = {c.id for c in categories if c.is_assignable}

        assert assignable == {offered.id}
