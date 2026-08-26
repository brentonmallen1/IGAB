"""A system tag's name is part of the mechanism: "Savings" renamed "Fun"
would still route money to the savings reports. Colour is cosmetic."""

from .factories import create_budget


async def _essential_tag(api_client, budget_id):
    listed = (await api_client.get(f"/api/v1/{budget_id}/tags")).json()
    return next(t for t in listed if t["system_key"] == "essential")


async def test_renaming_a_system_tag_is_refused(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    tag = await _essential_tag(api_client, budget.id)

    resp = await api_client.patch(f"/api/v1/{budget.id}/tags/{tag['id']}", json={"name": "Needs"})
    assert resp.status_code == 400
    assert "cannot be renamed" in resp.json()["detail"]
    assert (await _essential_tag(api_client, budget.id))["name"] == "Essential"


async def test_recolouring_a_system_tag_is_allowed(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    tag = await _essential_tag(api_client, budget.id)

    resp = await api_client.patch(
        f"/api/v1/{budget.id}/tags/{tag['id']}", json={"color_slot": "pink"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["color_slot"] == "pink" and resp.json()["name"] == "Essential"


async def test_sending_the_same_name_with_a_colour_is_not_a_rename(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    tag = await _essential_tag(api_client, budget.id)

    resp = await api_client.patch(
        f"/api/v1/{budget.id}/tags/{tag['id']}",
        json={"name": "Essential", "color_slot": "teal"},
    )
    assert resp.status_code == 200, resp.text
