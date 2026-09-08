"""Starred reports: a per-budget list the server keeps and does not interpret.

Twenty-nine reports behind a group dropdown is a fine way to find one you have
never opened and a poor way to return to the three you read every week.
"""

from igab.services.report_favorites import FAVORITES_KEY, MAX_FAVORITES

from .factories import create_budget


async def _get(api_client, budget_id) -> list[str]:
    r = await api_client.get(f"/api/v1/{budget_id}/reports/favorites")
    assert r.status_code == 200
    return r.json()["tabs"]


async def _put(api_client, budget_id, tabs) -> list[str]:
    r = await api_client.put(f"/api/v1/{budget_id}/reports/favorites", json={"tabs": tabs})
    assert r.status_code == 200
    return r.json()["tabs"]


async def test_a_budget_starts_with_none(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    assert await _get(api_client, budget.id) == []


async def test_stars_survive_the_round_trip_in_order(api_client, db_session):
    """Order is the user's — the row reads the way they arranged it — so the
    list must come back as it went in, not sorted."""
    budget = await create_budget(db_session, api_client.test_user)
    tabs = ["cost-of-living", "essentials", "net-worth"]
    assert await _put(api_client, budget.id, tabs) == tabs
    assert await _get(api_client, budget.id) == tabs


async def test_unstarring_the_last_one_removes_the_row(api_client, db_session):
    """An empty list is the absence of a preference, not a preference for
    nothing — a budget with no favourites should carry no favourites row."""
    from igab.guide.repo import GuideRepository

    budget = await create_budget(db_session, api_client.test_user)
    await _put(api_client, budget.id, ["essentials"])
    await _put(api_client, budget.id, [])

    assert await _get(api_client, budget.id) == []
    assert FAVORITES_KEY not in await GuideRepository(db_session).state(budget.id)


async def test_duplicates_and_blanks_are_dropped_keeping_the_first(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    sent = ["essentials", "  ", "net-worth", "essentials", ""]
    assert await _put(api_client, budget.id, sent) == ["essentials", "net-worth"]


async def test_the_list_is_capped(api_client, db_session):
    """Favourites are for the handful someone returns to; an unbounded list in
    a JSONB column is a row that grows without anyone deciding it should."""
    budget = await create_budget(db_session, api_client.test_user)
    kept = await _put(api_client, budget.id, [f"report-{i}" for i in range(40)])
    assert len(kept) == MAX_FAVORITES
    assert kept[0] == "report-0"


async def test_an_absurd_list_is_refused_rather_than_truncated(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    r = await api_client.put(
        f"/api/v1/{budget.id}/reports/favorites",
        json={"tabs": [f"report-{i}" for i in range(200)]},
    )
    assert r.status_code == 422


async def test_the_server_does_not_decide_which_reports_exist(api_client, db_session):
    """Which reports there are is a client fact — the ids are a TypeScript
    union and no backend path reads one. An allow-list here would be a second
    copy of the client's registry, kept in step by hand."""
    budget = await create_budget(db_session, api_client.test_user)
    assert await _put(api_client, budget.id, ["a-report-shipped-next-year"]) == [
        "a-report-shipped-next-year"
    ]


async def test_stars_are_per_budget(api_client, db_session):
    one = await create_budget(db_session, api_client.test_user)
    two = await create_budget(db_session, api_client.test_user)
    await _put(api_client, one.id, ["essentials"])
    assert await _get(api_client, two.id) == []


async def test_starring_is_undoable(api_client, db_session):
    """`set_state_recorded` is the shared writer for every Guide-state key, so
    a star lands in the change log like any other user decision."""
    budget = await create_budget(db_session, api_client.test_user)
    await _put(api_client, budget.id, ["essentials"])

    r = await api_client.get(f"/api/v1/{budget.id}/changes", params={"limit": 5})
    assert r.status_code == 200
    assert any(row["entity_type"] == "guide_state" for row in r.json()["changes"])
