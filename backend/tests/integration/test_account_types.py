"""Per-budget account-type registry: seeding, custom types, and the
derivation that keeps accounts.account_type/classification mirrors honest."""

from igab.domain.account_types import BUILTIN_ACCOUNT_TYPE_KEYS

from .factories import create_account, create_budget

BUILTIN_COUNT = len(BUILTIN_ACCOUNT_TYPE_KEYS)


async def _list_types(api_client, budget_id):
    resp = await api_client.get(f"/api/v1/{budget_id}/account-types")
    assert resp.status_code == 200
    return resp.json()


async def test_every_budget_creation_path_seeds_builtins(api_client):
    # Plain create
    resp = await api_client.post("/api/v1/budgets", json={"name": "Plain"})
    assert resp.status_code == 201
    rows = await _list_types(api_client, resp.json()["id"])
    assert {r["key"] for r in rows} == BUILTIN_ACCOUNT_TYPE_KEYS
    assert all(r["is_system"] for r in rows)

    # Sample budget
    resp = await api_client.post("/api/v1/budgets/create-sample", json={})
    assert resp.status_code == 201
    rows = await _list_types(api_client, resp.json()["budget"]["id"])
    assert {r["key"] for r in rows} == BUILTIN_ACCOUNT_TYPE_KEYS


async def test_list_orders_system_first(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    await api_client.post(
        f"/api/v1/{budget.id}/account-types",
        json={"label": "Aardvark Fund", "classification": "asset"},
    )
    rows = await _list_types(api_client, budget.id)
    # Custom row sorts after every built-in despite the alphabetical label
    assert [r["is_system"] for r in rows] == [True] * BUILTIN_COUNT + [False]


async def test_create_custom_type_slugifies_and_dedupes_key(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)

    resp = await api_client.post(
        f"/api/v1/{budget.id}/account-types",
        json={
            "label": "Crypto Wallet!",
            "classification": "asset",
            "default_on_budget": False,
            "description": "Cold storage",
        },
    )
    assert resp.status_code == 201
    first = resp.json()
    assert first["key"] == "crypto_wallet"
    assert first["is_system"] is False
    assert first["classification"] == "asset"

    resp = await api_client.post(
        f"/api/v1/{budget.id}/account-types",
        json={"label": "Crypto - Wallet", "classification": "asset"},
    )
    assert resp.status_code == 201
    assert resp.json()["key"] == "crypto_wallet_2"


async def test_account_creation_derives_from_type(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)

    # on_budget omitted → the type's default (loan defaults off-budget)
    resp = await api_client.post(
        f"/api/v1/{budget.id}/accounts", json={"name": "Mortgage", "account_type": "loan"}
    )
    assert resp.status_code == 201
    acc = resp.json()
    assert acc["on_budget"] is False
    assert acc["classification"] == "liability"

    # Explicit on_budget wins over the default
    resp = await api_client.post(
        f"/api/v1/{budget.id}/accounts",
        json={"name": "HELOC", "account_type": "loan", "on_budget": True},
    )
    assert resp.status_code == 201
    assert resp.json()["on_budget"] is True
    assert resp.json()["classification"] == "liability"

    # Custom type feeds the same derivation
    created = await api_client.post(
        f"/api/v1/{budget.id}/account-types",
        json={"label": "Timeshare", "classification": "liability", "default_on_budget": False},
    )
    resp = await api_client.post(
        f"/api/v1/{budget.id}/accounts",
        json={"name": "Maui Week 32", "account_type": created.json()["key"]},
    )
    assert resp.status_code == 201
    assert resp.json()["on_budget"] is False
    assert resp.json()["classification"] == "liability"


async def test_account_creation_rejects_unknown_type(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    resp = await api_client.post(
        f"/api/v1/{budget.id}/accounts", json={"name": "Boat", "account_type": "yacht"}
    )
    assert resp.status_code == 400
    assert "yacht" in resp.json()["detail"]


async def test_retyping_account_rederives_mirrors(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    acc = await create_account(db_session, budget, "Fidelity", account_type="checking")
    assert acc.classification == "asset"

    resp = await api_client.patch(
        f"/api/v1/accounts/{acc.id}", json={"account_type": "loan", "on_budget": False}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["account_type"] == "loan"
    assert body["classification"] == "liability"
    assert body["on_budget"] is False

    # Retyping without touching on_budget leaves it alone
    resp = await api_client.patch(f"/api/v1/accounts/{acc.id}", json={"account_type": "investment"})
    assert resp.status_code == 200
    assert resp.json()["classification"] == "asset"
    assert resp.json()["on_budget"] is False


async def test_custom_type_classification_edit_cascades_to_accounts(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    created = (
        await api_client.post(
            f"/api/v1/{budget.id}/account-types",
            json={"label": "Escrow", "classification": "asset", "default_on_budget": False},
        )
    ).json()
    acc = await create_account(db_session, budget, "Escrowed", account_type="escrow")
    assert acc.classification == "asset"

    resp = await api_client.patch(
        f"/api/v1/{budget.id}/account-types/{created['id']}", json={"classification": "liability"}
    )
    assert resp.status_code == 200

    fetched = await api_client.get(f"/api/v1/accounts/{acc.id}")
    assert fetched.json()["classification"] == "liability"


async def test_system_types_are_immutable(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    rows = await _list_types(api_client, budget.id)
    system_id = rows[0]["id"]

    resp = await api_client.patch(
        f"/api/v1/{budget.id}/account-types/{system_id}", json={"label": "Chequing"}
    )
    assert resp.status_code == 400
    resp = await api_client.delete(f"/api/v1/{budget.id}/account-types/{system_id}")
    assert resp.status_code == 400


async def test_delete_custom_type_blocked_while_referenced(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    created = (
        await api_client.post(
            f"/api/v1/{budget.id}/account-types",
            json={"label": "Pension", "classification": "asset", "default_on_budget": False},
        )
    ).json()
    acc = await create_account(db_session, budget, "Work Pension", account_type="pension")

    resp = await api_client.delete(f"/api/v1/{budget.id}/account-types/{created['id']}")
    assert resp.status_code == 409

    # Retype the account, then deletion goes through
    await api_client.patch(f"/api/v1/accounts/{acc.id}", json={"account_type": "investment"})
    resp = await api_client.delete(f"/api/v1/{budget.id}/account-types/{created['id']}")
    assert resp.status_code == 204
    rows = await _list_types(api_client, budget.id)
    assert "pension" not in {r["key"] for r in rows}


async def test_types_are_scoped_to_their_budget(api_client, db_session):
    budget_a = await create_budget(db_session, api_client.test_user)
    budget_b = await create_budget(db_session, api_client.test_user)
    created = (
        await api_client.post(
            f"/api/v1/{budget_a.id}/account-types",
            json={"label": "Only In A", "classification": "asset"},
        )
    ).json()

    # Not visible from the other budget, and unreachable through its paths
    rows_b = await _list_types(api_client, budget_b.id)
    assert "only_in_a" not in {r["key"] for r in rows_b}
    resp = await api_client.delete(f"/api/v1/{budget_b.id}/account-types/{created['id']}")
    assert resp.status_code == 404
    resp = await api_client.post(
        f"/api/v1/{budget_b.id}/accounts", json={"name": "Stray", "account_type": "only_in_a"}
    )
    assert resp.status_code == 400
