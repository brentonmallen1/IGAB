"""Which categories a picker may offer, decided once and served.

Six client components each spelled their own predicate, and the two rules they
were conflating differ on system groups: money must not be *assigned* into the
Income group, but income rows must be *filed* into it. A single flag would have
broken one of the two.

These are the served-field checklist from test_offbudget_categories.py, applied
to `is_assignable` and `is_categorizable`.
"""

from igab.api.v1.schemas.category import CategoryResponse
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository
from igab.repositories.tag_repo import TagRepository

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_tag,
    create_user,
)


async def _budget(db_session, user=None):
    user = user or await create_user(db_session)
    return await create_budget(db_session, user)


async def _tag(db_session, budget, category, system_key):
    """Tag a category with a system tag, making the tag row if the budget has
    none. The Emergency fund tag is not seeded yet, so its tests hand-make it."""
    repo = TagRepository(db_session)
    tag = await repo.get_system_tag(budget.id, system_key)
    if tag is None:
        tag = await create_tag(db_session, budget, system_key.title(), system_key=system_key)
    await repo.add_category_tag(category.id, tag.id)
    await db_session.flush()
    return tag


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
        await CategoryRepository(db_session).update(category.id, is_archived=True)

        loaded = await CategoryRepository(db_session).get(category.id)

        assert loaded.is_assignable is False
        assert loaded.is_categorizable is False

    async def test_a_category_in_a_hidden_group_is_neither(self, db_session):
        # The leak: CategoryRepository.get_all filters the category's is_archived
        # but not the group's, while CategoryGroupRepository.get_all filters the
        # group's. So these arrived at the client without their group.
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Archive")
        await CategoryGroupRepository(db_session).update(group.id, is_archived=True)
        category = await create_category(db_session, budget, group, "Stale")

        loaded = await CategoryRepository(db_session).get(category.id)

        assert loaded.is_assignable is False
        assert loaded.is_categorizable is False

    async def test_a_linked_payment_category_is_funded_but_never_offered(self, db_session):
        """A credit-card's envelope holds budgeted money — that is how a
        card is paid down — but no picker lists it and nothing may be filed to
        it. Three questions, three answers.

        This asserted `is_assignable is True` until the two questions were
        split. Measuring a real envelope showed that claim only held for a
        configuration `ensure_payment_category` never builds: it puts the
        envelope in a hidden group, so `is_assignable` came back False anyway
        and `assign_service` had never funded a card target."""
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Credit Cards")
        category = await create_category(db_session, budget, group, "Visa")
        account = await create_account(db_session, budget, "Visa", account_type="credit_card")
        await CategoryRepository(db_session).update(category.id, linked_account_id=account.id)

        loaded = await CategoryRepository(db_session).get(category.id)

        assert loaded.is_assignable is False  # no picker offers it
        assert loaded.is_fundable is True  # money still goes in
        assert loaded.is_categorizable is False  # nothing is filed to it


class TestEveryPathCarriesTheFlags:
    async def test_get_all_carries_them(self, db_session):
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Everyday")
        await create_category(db_session, budget, group, "Groceries")

        for category in await CategoryRepository(db_session).get_all(budget.id):
            assert category.is_assignable is not None
            assert category.is_categorizable is not None
            assert category.savings_role == "none"

    async def test_every_listing_path_carries_the_savings_role(self, db_session):
        """`get_all_with_group_names` spelled its expressions out by hand, and
        `get_taggable_with_group_names` loaded none: a served field added to
        `with_eligibility` alone would have been missing from both."""
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Goals")
        category = await create_category(db_session, budget, group, "Rainy Day")
        await _tag(db_session, budget, category, "savings")
        repo = CategoryRepository(db_session)

        paths = {
            "get": [await repo.get(category.id)],
            "get_all": await repo.get_all(budget.id),
            "get_with_tags": [await repo.get_with_tags(category.id)],
            "get_all_with_group_names": [
                c for c, _ in await repo.get_all_with_group_names(budget.id)
            ],
            "get_fileable_with_group_names": [
                c for c, _ in await repo.get_fileable_with_group_names(budget.id)
            ],
            "get_taggable_with_group_names": [
                c for c, _ in await repo.get_taggable_with_group_names(budget.id, None)
            ],
        }
        for path, rows in paths.items():
            [row] = [r for r in rows if r.id == category.id]
            assert row.savings_role == "sent_out", path

    async def test_savings_role_follows_a_tag_added_elsewhere(self, db_session):
        """The reason it cannot be a column: a tag write never touches the
        category row."""
        budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, "Goals")
        category = await create_category(db_session, budget, group, "Rainy Day")
        repo = CategoryRepository(db_session)

        assert (await repo.get(category.id)).savings_role == "none"

        await _tag(db_session, budget, category, "savings")

        assert (await repo.get(category.id)).savings_role == "sent_out"
        [listed] = await repo.get_all(budget.id)
        assert listed.savings_role == "sent_out"

    async def test_every_mutating_endpoint_returns_a_serializable_row(self, db_session, api_client):
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

        assert resp.json()["savings_role"] == "none"
        assert resp.json()["savings_mode"] is None

        resp = await api_client.get(f"/api/v1/{budget.id}/categories")
        assert resp.status_code == 200, resp.text
        assert all("is_assignable" in c for c in resp.json())
        assert all("savings_role" in c for c in resp.json())

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
        everyday = await create_category_group(db_session, budget, "Everyday")
        income = await _system_group(db_session, budget)
        hidden_group = await create_category_group(db_session, budget, "Archive")
        await CategoryGroupRepository(db_session).update(hidden_group.id, is_archived=True)

        offered = await create_category(db_session, budget, everyday, "Groceries")
        await create_category(db_session, budget, income, "Paycheque")
        await create_category(db_session, budget, hidden_group, "Stale")

        categories = await CategoryRepository(db_session).get_all(budget.id)
        assignable = {c.id for c in categories if c.is_assignable}

        assert assignable == {offered.id}

    async def test_the_ai_filing_list_is_exactly_the_categorizable_set(self, db_session):
        """What the model is shown and matched against, and what `require_categorizable`
        lets a row be filed to, must be one set. The naming list beside it
        keeps what its readers (the chat tools, the YNAB import, parity,
        export) always had."""
        budget = await _budget(db_session)
        everyday = await create_category_group(db_session, budget, "Everyday")
        income = await _system_group(db_session, budget)
        hidden_group = await create_category_group(db_session, budget, "Archive")
        await CategoryGroupRepository(db_session).update(hidden_group.id, is_archived=True)
        cards = await create_category_group(db_session, budget, "Credit Card Payments")
        repo = CategoryRepository(db_session)

        groceries = await create_category(db_session, budget, everyday, "Groceries")
        paycheque = await create_category(db_session, budget, income, "Paycheque")
        stale = await create_category(db_session, budget, hidden_group, "Stale")
        envelope = await create_category(db_session, budget, cards, "Sapphire Visa")
        card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
        await repo.update(envelope.id, linked_account_id=card.id)
        retired = await create_category(db_session, budget, everyday, "Retired")
        await repo.update(retired.id, is_archived=True)

        fileable = {c.id for c, _ in await repo.get_fileable_with_group_names(budget.id)}
        categorizable = {c.id for c in await repo.get_all(budget.id) if c.is_categorizable}
        assert fileable == categorizable == {groceries.id, paycheque.id}

        named = {c.id for c, _ in await repo.get_all_with_group_names(budget.id)}
        assert named == {groceries.id, paycheque.id, stale.id, envelope.id}
        with_archived = await repo.get_all_with_group_names(budget.id, include_archived=True)
        assert {c.id for c, _ in with_archived} == named | {retired.id}


class TestSavingsRole:
    """How a category's money counts as saved: a stored choice, and a default
    the tags imply. Served as `savings_role`; `savings_mode` is only the
    choice."""

    async def _category(self, db_session, api_client=None):
        user = api_client.test_user if api_client is not None else None
        budget = await _budget(db_session, user)
        group = await create_category_group(db_session, budget, "Goals")
        category = await create_category(db_session, budget, group, "Emergency Fund")
        return budget, category

    async def test_an_untagged_category_serves_none(self, db_session):
        _, category = await self._category(db_session)
        assert (await CategoryRepository(db_session).get(category.id)).savings_role == "none"

    async def test_a_savings_tag_defaults_to_sent_out(self, db_session):
        """What the Savings tag always meant, so no existing figure moves."""
        budget, category = await self._category(db_session)
        await _tag(db_session, budget, category, "savings")
        assert (await CategoryRepository(db_session).get(category.id)).savings_role == "sent_out"

    async def test_emergency_fund_tag_implies_savings_and_defaults_kept_here(self, db_session):
        budget, category = await self._category(db_session)
        await _tag(db_session, budget, category, "emergency_fund")
        assert (await CategoryRepository(db_session).get(category.id)).savings_role == "kept_here"

    async def test_both_tags_with_no_choice_default_kept_here(self, db_session):
        budget, category = await self._category(db_session)
        await _tag(db_session, budget, category, "savings")
        await _tag(db_session, budget, category, "emergency_fund")
        assert (await CategoryRepository(db_session).get(category.id)).savings_role == "kept_here"

    async def test_explicit_mode_overrides_the_emergency_fund_default(self, db_session, api_client):
        budget, category = await self._category(db_session, api_client)
        await _tag(db_session, budget, category, "emergency_fund")

        resp = await api_client.patch(
            f"/api/v1/categories/{category.id}", json={"savings_mode": "sent_out"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["savings_mode"] == "sent_out"
        assert resp.json()["savings_role"] == "sent_out"

        # An explicit null clears the choice back to the tag's default.
        resp = await api_client.patch(
            f"/api/v1/categories/{category.id}", json={"savings_mode": None}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["savings_mode"] is None
        assert resp.json()["savings_role"] == "kept_here"

    async def test_an_explicit_kept_here_overrides_the_savings_default(
        self, db_session, api_client
    ):
        budget, category = await self._category(db_session, api_client)
        await _tag(db_session, budget, category, "savings")
        resp = await api_client.patch(
            f"/api/v1/categories/{category.id}", json={"savings_mode": "kept_here"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["savings_role"] == "kept_here"

    async def test_removing_both_tags_serves_none_and_keeps_the_stored_choice(
        self, db_session, api_client
    ):
        budget, category = await self._category(db_session, api_client)
        savings = await _tag(db_session, budget, category, "savings")
        emergency = await _tag(db_session, budget, category, "emergency_fund")
        resp = await api_client.patch(
            f"/api/v1/categories/{category.id}", json={"savings_mode": "sent_out"}
        )
        assert resp.status_code == 200, resp.text

        repo = TagRepository(db_session)
        await repo.remove_category_tag(category.id, savings.id)
        await repo.remove_category_tag(category.id, emergency.id)
        await db_session.flush()

        loaded = await CategoryRepository(db_session).get(category.id)
        assert loaded.savings_role == "none"
        assert loaded.savings_mode == "sent_out", "re-tagging brings the choice back"

        await repo.add_category_tag(category.id, emergency.id)
        await db_session.flush()
        assert (await CategoryRepository(db_session).get(category.id)).savings_role == "sent_out"

    async def test_a_mode_may_be_set_on_an_untagged_category(self, db_session, api_client):
        _, category = await self._category(db_session, api_client)
        resp = await api_client.patch(
            f"/api/v1/categories/{category.id}", json={"savings_mode": "kept_here"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["savings_mode"] == "kept_here"
        assert resp.json()["savings_role"] == "none"

    async def test_an_unknown_mode_is_refused(self, db_session, api_client):
        _, category = await self._category(db_session, api_client)
        resp = await api_client.patch(
            f"/api/v1/categories/{category.id}", json={"savings_mode": "invested"}
        )
        assert resp.status_code == 422, resp.text

    async def test_a_deleted_emergency_fund_tag_no_longer_implies_savings(self, db_session):
        budget, category = await self._category(db_session)
        tag = await _tag(db_session, budget, category, "emergency_fund")
        tag.is_deleted = True
        await db_session.flush()
        assert (await CategoryRepository(db_session).get(category.id)).savings_role == "none"

    async def test_undo_restores_savings_mode(self, db_session, api_client):
        """Undo restores the fields `change_log` snapshots and nothing else, so
        a mode missing from the "category" tuple would record an edit that ⌘Z
        reports undoing while the envelope keeps counting the new way."""
        budget, category = await self._category(db_session, api_client)
        await _tag(db_session, budget, category, "savings")
        resp = await api_client.patch(
            f"/api/v1/categories/{category.id}", json={"savings_mode": "kept_here"}
        )
        assert resp.status_code == 200, resp.text

        resp = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert resp.status_code == 200, resp.text
        assert (resp.json()["entity_type"], resp.json()["action"]) == ("category", "update")

        loaded = await CategoryRepository(db_session).get(category.id)
        assert loaded.savings_mode is None
        assert loaded.savings_role == "sent_out"


class TestTheModeIsSpelledOnce:
    def test_the_check_constraint_names_exactly_the_served_modes(self):
        """The model's constraint cannot import `SavingsMode` (the filters
        module imports the model), so it is pinned here instead."""
        from typing import get_args

        from sqlalchemy import CheckConstraint

        from igab.db.models import Category
        from igab.repositories.category_filters import SavingsMode

        [constraint] = [
            c
            for c in Category.__table__.constraints
            if isinstance(c, CheckConstraint) and c.name == "ck_categories_savings_mode"
        ]
        text = str(constraint.sqltext)
        for mode in get_args(SavingsMode):
            assert f"'{mode}'" in text
        assert text.count("'") == 2 * len(get_args(SavingsMode))
