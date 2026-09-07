"""A paycheck can be named.

"Paycheck 2" says nothing about which paycheck it is. The label rides in the
plan document like every other planner field — draft-permissive storage, so
an empty name is absent rather than "".
"""

from .factories import create_budget


async def _plan(api_client, budget):
    r = await api_client.post(f"/api/v1/{budget.id}/category-plans", json={})
    assert r.status_code == 201, r.text
    return r.json()


async def test_a_label_round_trips_and_survives_a_reload(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()
    plan = await _plan(api_client, budget)
    payload = plan["payload"]
    payload["paychecks"][0]["label"] = "Northwind, 1st"

    r = await api_client.put(
        f"/api/v1/{budget.id}/category-plans/{plan['id']}", json={"payload": payload}
    )
    assert r.status_code == 200, r.text

    again = (await api_client.get(f"/api/v1/{budget.id}/category-plans/{plan['id']}")).json()
    assert again["payload"]["paychecks"][0]["label"] == "Northwind, 1st"


async def test_an_absent_label_is_null_not_empty_string(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()
    plan = await _plan(api_client, budget)
    assert all(p["label"] is None for p in plan["payload"]["paychecks"])


async def test_an_overlong_label_is_refused(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.commit()
    plan = await _plan(api_client, budget)
    payload = plan["payload"]
    payload["paychecks"][0]["label"] = "x" * 61
    r = await api_client.put(
        f"/api/v1/{budget.id}/category-plans/{plan['id']}", json={"payload": payload}
    )
    assert r.status_code == 422
