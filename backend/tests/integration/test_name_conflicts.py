"""Naming two things the same is an ordinary mistake, and every resource that
can suffer it must answer 409 rather than 500.

It was handled per-router, so the filters router shipped without the handling
its sibling views router received in the very same change — and the views
router's own handler was too broad, reporting a duplicate PLACEMENT as
'a view named "" already exists'. Both are now the job of one IntegrityError
handler that reads the constraint that actually failed, so a resource cannot
forget: adding the constraint is what registers the message.
"""

import uuid

from .factories import (
    create_budget,
    create_category,
    create_category_group,
)


async def _budget(db_session, api_client):
    return await create_budget(db_session, api_client.test_user)


class TestFilters:
    async def test_duplicate_name_is_a_conflict(self, api_client, db_session):
        budget = await _budget(db_session, api_client)
        first = await api_client.post(f"/api/v1/{budget.id}/filters", json={"name": "Bills"})
        second = await api_client.post(f"/api/v1/{budget.id}/filters", json={"name": "Bills"})

        assert first.status_code == 201
        assert second.status_code == 409
        assert "filter" in second.json()["detail"].lower()

    async def test_renaming_onto_an_existing_name_is_a_conflict(self, api_client, db_session):
        budget = await _budget(db_session, api_client)
        await api_client.post(f"/api/v1/{budget.id}/filters", json={"name": "Bills"})
        other = await api_client.post(f"/api/v1/{budget.id}/filters", json={"name": "Fun"})

        resp = await api_client.patch(
            f"/api/v1/filters/{other.json()['id']}", json={"name": "Bills"}
        )

        assert resp.status_code == 409

    async def test_the_same_name_in_another_budget_is_fine(self, api_client, db_session):
        a = await _budget(db_session, api_client)
        b = await _budget(db_session, api_client)
        await api_client.post(f"/api/v1/{a.id}/filters", json={"name": "Bills"})

        resp = await api_client.post(f"/api/v1/{b.id}/filters", json={"name": "Bills"})

        assert resp.status_code == 201


class TestViews:
    async def test_duplicate_name_is_a_conflict(self, api_client, db_session):
        budget = await _budget(db_session, api_client)
        await api_client.post(f"/api/v1/{budget.id}/views", json={"name": "Need / Want"})

        resp = await api_client.post(f"/api/v1/{budget.id}/views", json={"name": "Need / Want"})

        assert resp.status_code == 409
        assert "view" in resp.json()["detail"].lower()

    async def test_a_duplicate_placement_says_so(self, api_client, db_session):
        """Not 'a view named "" already exists' — the old catch-all reported
        every IntegrityError from this endpoint as a name collision."""
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Everyday")
        cat = await create_category(db_session, budget, group, "Dining")
        view = (
            await api_client.post(
                f"/api/v1/{budget.id}/views", json={"name": "Lens", "groups": ["Need", "Save"]}
            )
        ).json()

        resp = await api_client.patch(
            f"/api/v1/views/{view['id']}",
            json={
                "placements": [
                    {"category_id": str(cat.id), "group_name": "Need"},
                    {"category_id": str(cat.id), "group_name": "Save"},
                ]
            },
        )

        assert resp.status_code == 409
        detail = resp.json()["detail"].lower()
        assert "placed" in detail or "category" in detail
        assert "named" not in detail, "must not be reported as a name collision"


class TestCategories:
    async def test_duplicate_category_name_in_a_group_is_a_conflict(
        self, api_client, db_session
    ):
        """Previously a 500 — the follow-up recorded when views gained their
        own handler and nothing else did."""
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Everyday")
        await create_category(db_session, budget, group, "Dining")

        resp = await api_client.post(
            f"/api/v1/{budget.id}/categories",
            json={"name": "Dining", "category_group_id": str(group.id)},
        )

        assert resp.status_code == 409

    async def test_duplicate_group_name_is_a_conflict(self, api_client, db_session):
        budget = await _budget(db_session, api_client)
        await create_category_group(db_session, budget, "Everyday")

        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups", json={"name": "Everyday"}
        )

        assert resp.status_code == 409


class TestNamesFreedByDeletion:
    """Deletes are soft; the unique constraints were not.

    a4c9e17d3b58 scoped budget_views and budget_filters to live rows and left
    accounts, payees, category groups, categories and tags carrying the
    defect. Deleting an account burned its name forever, so recreating it
    answered "An account with that name already exists in this budget"
    against a list showing no such account. Reported from production on
    v2026.08.17.
    """

    async def test_an_accounts_name_is_reusable_after_deletion(self, api_client, db_session):
        budget = await _budget(db_session, api_client)
        created = await api_client.post(
            f"/api/v1/{budget.id}/accounts", json={"name": "Harborstone", "account_type": "checking"}
        )
        assert created.status_code == 201
        assert (await api_client.delete(f"/api/v1/accounts/{created.json()['id']}")).status_code == 204

        again = await api_client.post(
            f"/api/v1/{budget.id}/accounts", json={"name": "Harborstone", "account_type": "checking"}
        )

        assert again.status_code == 201, again.json()

    async def test_a_categorys_name_is_reusable_after_undoing_its_creation(
        self, api_client, db_session
    ):
        """Undo-of-create soft-deletes the row (undo_service._undo_create), so
        it burns the name by the same mechanism a delete does. Reachable for
        every entity in ENTITY_MODELS — categories, groups, payees — but NOT
        for accounts, which are not undoable at all.
        """
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget)
        created = await api_client.post(
            f"/api/v1/{budget.id}/categories",
            json={"category_group_id": str(group.id), "name": "Annual Insurance"},
        )
        assert created.status_code == 201
        changes = await api_client.get(f"/api/v1/{budget.id}/changes")
        newest = changes.json()["changes"][0]["id"]
        assert (
            await api_client.post(f"/api/v1/{budget.id}/changes/{newest}/undo")
        ).status_code == 200

        again = await api_client.post(
            f"/api/v1/{budget.id}/categories",
            json={"category_group_id": str(group.id), "name": "Annual Insurance"},
        )

        assert again.status_code == 201, again.json()

    async def test_an_account_can_be_renamed_onto_a_deleted_rows_name(
        self, api_client, db_session
    ):
        """The rename path is a different statement (UPDATE, not INSERT) but
        the same index decides it. Creating under a workaround name and then
        renaming to the one you wanted is the obvious way out of the bug, so
        it has to work too.
        """
        budget = await _budget(db_session, api_client)
        first = await api_client.post(
            f"/api/v1/{budget.id}/accounts", json={"name": "Harborstone", "account_type": "checking"}
        )
        assert (await api_client.delete(f"/api/v1/accounts/{first.json()['id']}")).status_code == 204
        stand_in = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Harborstone 2", "account_type": "checking"},
        )

        renamed = await api_client.patch(
            f"/api/v1/accounts/{stand_in.json()['id']}", json={"name": "Harborstone"}
        )

        assert renamed.status_code == 200, renamed.json()
        assert renamed.json()["name"] == "Harborstone"

    async def test_renaming_onto_a_live_accounts_name_is_still_a_conflict(
        self, api_client, db_session
    ):
        budget = await _budget(db_session, api_client)
        await api_client.post(
            f"/api/v1/{budget.id}/accounts", json={"name": "Harborstone", "account_type": "checking"}
        )
        other = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Cascade Point HYSA", "account_type": "savings"},
        )

        resp = await api_client.patch(
            f"/api/v1/accounts/{other.json()['id']}", json={"name": "Harborstone"}
        )

        assert resp.status_code == 409
        assert "account with that name already exists" in resp.json()["detail"].lower()

    async def test_a_live_duplicate_account_name_is_still_a_conflict(self, api_client, db_session):
        """The constraint was renamed, and _UNIQUE_CONSTRAINT_DETAIL is keyed
        by constraint name — so a stale key would turn this 409 into a 500.
        """
        budget = await _budget(db_session, api_client)
        await api_client.post(
            f"/api/v1/{budget.id}/accounts", json={"name": "Harborstone", "account_type": "checking"}
        )

        dupe = await api_client.post(
            f"/api/v1/{budget.id}/accounts", json={"name": "Harborstone", "account_type": "checking"}
        )

        assert dupe.status_code == 409
        assert "account with that name already exists" in dupe.json()["detail"].lower()

    async def test_a_category_name_is_reusable_after_deletion(self, api_client, db_session):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget)
        cat = await create_category(db_session, budget, group, name="Groceries")
        assert (await api_client.delete(f"/api/v1/categories/{cat.id}")).status_code == 200

        again = await api_client.post(
            f"/api/v1/{budget.id}/categories",
            json={"category_group_id": str(group.id), "name": "Groceries"},
        )

        assert again.status_code == 201, again.json()

    async def test_a_group_name_is_reusable_after_deletion(self, api_client, db_session):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, name="Seasonal")
        assert (await api_client.delete(f"/api/v1/category-groups/{group.id}")).status_code == 200

        again = await api_client.post(
            f"/api/v1/{budget.id}/category-groups", json={"name": "Seasonal"}
        )

        assert again.status_code == 201, again.json()


class TestUnrecognisedIntegrityErrorsStayFaults:
    async def test_a_foreign_key_violation_is_not_dressed_up_as_a_conflict(
        self, api_client, db_session
    ):
        """The handler must only claim the collisions it has copy for. A
        genuine fault reported as 409 tells the user to rename something."""
        budget = await _budget(db_session, api_client)

        resp = await api_client.post(
            f"/api/v1/{budget.id}/categories",
            json={"name": "Orphan", "category_group_id": str(uuid.uuid4())},
        )

        assert resp.status_code != 409
