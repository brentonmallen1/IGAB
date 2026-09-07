"""A group that looks empty on the budget page, and is not.

The grid draws no archived envelope. So a group whose categories have all been
archived draws as a bare heading with nothing under it — while every endpoint
that acts on the group still sees a group full of envelopes. Delete it and the
dialog names categories that are nowhere on the page; archive it and an
archived envelope's own balance can refuse the whole thing.

Reported as "I moved the categories out and it still says they are in there".
They had not been moved, and this is why the page could not say so: nothing on
the grid distinguished *empty* from *nothing drawn here*. The count is served
(`GROUP_ARCHIVED_CATEGORY_COUNT` → `CategoryGroupResponse.archived_category_count`)
because the client cannot compute it — its category list is fetched without
`include_archived`, so the rows are simply not there.

The last class is the other half of the report, and the reason no migration was
owed: a move really does move, and the old group really does stop naming it.
"""

import pytest

from igab.repositories.category_repo import CategoryGroupRepository

from .factories import (
    create_budget,
    create_category,
    create_category_group,
)


async def _archive(api_client, budget, *categories):
    resp = await api_client.post(
        f"/api/v1/{budget.id}/categories/archive",
        json={"category_ids": [str(c.id) for c in categories], "month": "2026-09-01"},
    )
    assert resp.status_code == 200, resp.text
    return resp


async def _listed(api_client, budget) -> dict[str, dict]:
    resp = await api_client.get(f"/api/v1/{budget.id}/category-groups")
    assert resp.status_code == 200, resp.text
    return {g["name"]: g for g in resp.json()}


@pytest.fixture
async def budget_with_two_groups(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    keep = await create_category_group(db_session, budget, "Everyday")
    tidy = await create_category_group(db_session, budget, "Fitness")
    coaching = await create_category(db_session, budget, tidy, "Coaching")
    equipment = await create_category(db_session, budget, tidy, "Equipment")
    return budget, keep, tidy, coaching, equipment


class TestTheCountIsServedEverywhere:
    """Required in the schema, so a path that forgets the loader raises. These
    say which paths there are, because every one of them is a place a group is
    drawn."""

    async def test_the_listing_carries_it(self, api_client, budget_with_two_groups):
        budget, _keep, tidy, coaching, equipment = budget_with_two_groups
        assert (await _listed(api_client, budget))["Fitness"]["archived_category_count"] == 0

        await _archive(api_client, budget, coaching, equipment)
        listed = await _listed(api_client, budget)
        assert listed["Fitness"]["archived_category_count"] == 2
        assert listed["Everyday"]["archived_category_count"] == 0
        assert tidy.name == "Fitness"

    async def test_create_returns_a_serializable_group(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups", json={"name": "Sabbatical"}
        )
        assert resp.status_code == 201, resp.text
        # A brand-new group holds nothing, archived or otherwise — and the
        # field must be *present*, not merely falsy, or the schema would have
        # let the create path skip the loader.
        assert resp.json()["archived_category_count"] == 0

    async def test_a_rename_still_carries_it(self, api_client, budget_with_two_groups):
        budget, _keep, tidy, coaching, equipment = budget_with_two_groups
        await _archive(api_client, budget, coaching, equipment)
        resp = await api_client.patch(
            f"/api/v1/category-groups/{tidy.id}", json={"name": "Fitness (old)"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["archived_category_count"] == 2


class TestWhatItCounts:
    async def test_it_tracks_archiving_and_unarchiving(
        self, api_client, budget_with_two_groups, db_session
    ):
        budget, _keep, _tidy, coaching, equipment = budget_with_two_groups
        await _archive(api_client, budget, coaching)
        assert (await _listed(api_client, budget))["Fitness"]["archived_category_count"] == 1

        await _archive(api_client, budget, equipment)
        assert (await _listed(api_client, budget))["Fitness"]["archived_category_count"] == 2

        resp = await api_client.post(
            f"/api/v1/{budget.id}/categories/unarchive",
            json={"category_ids": [str(coaching.id)], "month": "2026-09-01"},
        )
        assert resp.status_code == 200, resp.text
        assert (await _listed(api_client, budget))["Fitness"]["archived_category_count"] == 1

    async def test_a_soft_deleted_category_does_not_count(
        self, api_client, budget_with_two_groups, db_session
    ):
        """Deleted is gone, not put away. Counting one would tell the user to
        go looking in the archived room for something that is not there."""
        budget, _keep, _tidy, coaching, equipment = budget_with_two_groups
        await _archive(api_client, budget, coaching, equipment)
        resp = await api_client.delete(f"/api/v1/categories/{equipment.id}")
        assert resp.status_code == 200, resp.text
        assert (await _listed(api_client, budget))["Fitness"]["archived_category_count"] == 1

    async def test_it_follows_the_category_to_its_new_group(
        self, api_client, budget_with_two_groups
    ):
        """Archived is a state, not a place. Moving an archived envelope moves
        the count with it — the alternative is a group that keeps reporting an
        envelope it no longer holds, which is the exact complaint."""
        budget, keep, _tidy, coaching, equipment = budget_with_two_groups
        await _archive(api_client, budget, coaching, equipment)
        resp = await api_client.patch(
            f"/api/v1/categories/{coaching.id}", json={"category_group_id": str(keep.id)}
        )
        assert resp.status_code == 200, resp.text

        listed = await _listed(api_client, budget)
        assert listed["Fitness"]["archived_category_count"] == 1
        assert listed["Everyday"]["archived_category_count"] == 1

    async def test_the_group_flag_is_a_separate_fact(
        self, api_client, budget_with_two_groups, db_session
    ):
        """Archiving the GROUP sets the group's own flag and touches no
        category (`archive_group` says why). The count must not move with it,
        or restoring the group would restore envelopes that were archived on
        their own merits."""
        budget, _keep, tidy, coaching, _equipment = budget_with_two_groups
        await _archive(api_client, budget, coaching)
        resp = await api_client.post(
            f"/api/v1/{budget.id}/category-groups/{tidy.id}/archive",
            json={"month": "2026-09-01"},
        )
        assert resp.status_code == 200, resp.text

        db_session.expunge_all()
        groups = await CategoryGroupRepository(db_session).get_all(budget.id, include_archived=True)
        tidy_row = next(g for g in groups if g.name == "Fitness")
        assert tidy_row.is_archived is True
        assert tidy_row.archived_category_count == 1


class TestTheEmptyGroupTheGridDrew:
    """The two answers that used to disagree, asked side by side."""

    async def test_a_group_of_archived_envelopes_is_not_empty(
        self, api_client, budget_with_two_groups
    ):
        budget, _keep, tidy, coaching, equipment = budget_with_two_groups
        await _archive(api_client, budget, coaching, equipment)

        # What the grid gets: no rows for this group at all.
        drawn = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        assert [c for c in drawn if c["category_group_id"] == str(tidy.id)] == []

        # What the delete dialog gets: two categories, named.
        preview = (await api_client.get(f"/api/v1/category-groups/{tidy.id}/delete-preview")).json()
        assert sorted(preview["category_names"]) == ["Coaching", "Equipment"]
        assert preview["archived_count"] == 2
        assert preview["all_archived"] is True

        # And the one field that lets the grid say the same thing the dialog
        # does, instead of drawing a heading over nothing.
        assert (await _listed(api_client, budget))["Fitness"]["archived_category_count"] == 2

    async def test_a_group_that_really_is_empty_says_zero(self, api_client, budget_with_two_groups):
        budget, keep, tidy, coaching, equipment = budget_with_two_groups
        for category in (coaching, equipment):
            resp = await api_client.patch(
                f"/api/v1/categories/{category.id}",
                json={"category_group_id": str(keep.id)},
            )
            assert resp.status_code == 200, resp.text

        assert (await _listed(api_client, budget))["Fitness"]["archived_category_count"] == 0
        preview = (await api_client.get(f"/api/v1/category-groups/{tidy.id}/delete-preview")).json()
        assert preview["category_names"] == []


class TestMovingACategoryReallyMovesIt:
    """The half of the report that turned out not to be a defect. Pinned
    anyway: the claim was that a move did nothing to the relationship, and a
    test is cheaper than reading the change log again."""

    async def test_the_old_group_stops_naming_it(self, api_client, budget_with_two_groups):
        budget, keep, tidy, coaching, _equipment = budget_with_two_groups
        resp = await api_client.patch(
            f"/api/v1/categories/{coaching.id}", json={"category_group_id": str(keep.id)}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["category_group_id"] == str(keep.id)

        old = (await api_client.get(f"/api/v1/category-groups/{tidy.id}/delete-preview")).json()
        new = (await api_client.get(f"/api/v1/category-groups/{keep.id}/delete-preview")).json()
        assert old["category_names"] == ["Equipment"]
        assert new["category_names"] == ["Coaching"]

    async def test_the_move_survives_a_reload(self, api_client, budget_with_two_groups, db_session):
        budget, keep, _tidy, coaching, _equipment = budget_with_two_groups
        await api_client.patch(
            f"/api/v1/categories/{coaching.id}", json={"category_group_id": str(keep.id)}
        )
        db_session.expunge_all()
        listed = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        moved = next(c for c in listed if c["name"] == "Coaching")
        assert moved["category_group_id"] == str(keep.id)
