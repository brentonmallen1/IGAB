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

import pytest

from .factories import (
    create_budget,
    create_category,
    create_category_group,
    create_user,
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
