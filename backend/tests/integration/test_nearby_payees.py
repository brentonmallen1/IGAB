"""Nearby-payee suggestions: located transactions power `/payees/nearby`.

Coordinates are opt-in metadata and must never influence money math — the
final test pins that with the conservation invariant checker.

Geometry note: at 40°N, 0.001° latitude ≈ 111.2 m and 0.001° longitude ≈ 85.2 m.
"""

from datetime import date

from .factories import (
    create_account,
    create_budget,
    create_payee,
    create_transaction,
)
from .invariants import assert_financial_invariants

HOME_LAT, HOME_LNG = 40.0, -75.0


async def _seed(db_session, user):
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")

    grocery = await create_payee(db_session, budget, "Grocery Store")
    coffee = await create_payee(db_session, budget, "Coffee Shop")
    farmall = await create_payee(db_session, budget, "Far Away Hardware")
    unlocated = await create_payee(db_session, budget, "Online Retailer")

    # Grocery: two visits ~55.6 m and ~111.2 m north of home
    await create_transaction(
        db_session,
        budget,
        account,
        "-20.00",
        date(2026, 7, 1),
        payee=grocery,
        latitude=HOME_LAT + 0.0005,
        longitude=HOME_LNG,
    )
    await create_transaction(
        db_session,
        budget,
        account,
        "-35.00",
        date(2026, 7, 15),
        payee=grocery,
        latitude=HOME_LAT + 0.001,
        longitude=HOME_LNG,
    )
    # Coffee: one visit ~333.6 m north
    await create_transaction(
        db_session,
        budget,
        account,
        "-4.50",
        date(2026, 7, 10),
        payee=coffee,
        latitude=HOME_LAT + 0.003,
        longitude=HOME_LNG,
    )
    # Hardware: ~2224 m away — outside a 500 m radius
    await create_transaction(
        db_session,
        budget,
        account,
        "-60.00",
        date(2026, 7, 5),
        payee=farmall,
        latitude=HOME_LAT + 0.02,
        longitude=HOME_LNG,
    )
    # Unlocated visit contributes nothing
    await create_transaction(
        db_session,
        budget,
        account,
        "-15.00",
        date(2026, 7, 8),
        payee=unlocated,
    )
    return budget, account


async def test_nearby_orders_by_distance_within_radius(api_client, db_session):
    budget, _ = await _seed(db_session, api_client.test_user)

    resp = await api_client.get(
        f"/api/v1/{budget.id}/payees/nearby",
        params={"lat": HOME_LAT, "lng": HOME_LNG, "radius_m": 500},
    )
    assert resp.status_code == 200
    payees = resp.json()

    assert [p["name"] for p in payees] == ["Grocery Store", "Coffee Shop"]

    grocery = payees[0]
    assert grocery["visit_count"] == 2
    assert grocery["last_date"] == "2026-07-15"
    # Min distance across visits: the ~55.6 m one
    assert 50 < grocery["distance_m"] < 62

    coffee = payees[1]
    assert coffee["visit_count"] == 1
    assert 325 < coffee["distance_m"] < 342


async def test_nearby_radius_excludes_and_limit_truncates(api_client, db_session):
    budget, _ = await _seed(db_session, api_client.test_user)

    # Wide radius picks up the hardware store too
    resp = await api_client.get(
        f"/api/v1/{budget.id}/payees/nearby",
        params={"lat": HOME_LAT, "lng": HOME_LNG, "radius_m": 5000},
    )
    names = [p["name"] for p in resp.json()]
    assert names == ["Grocery Store", "Coffee Shop", "Far Away Hardware"]

    # limit truncates after distance ranking
    resp = await api_client.get(
        f"/api/v1/{budget.id}/payees/nearby",
        params={"lat": HOME_LAT, "lng": HOME_LNG, "radius_m": 5000, "limit": 1},
    )
    assert [p["name"] for p in resp.json()] == ["Grocery Store"]


async def test_nearby_validates_coordinates(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)

    resp = await api_client.get(f"/api/v1/{budget.id}/payees/nearby", params={"lat": 91, "lng": 0})
    assert resp.status_code == 422

    resp = await api_client.get(f"/api/v1/{budget.id}/payees/nearby", params={"lat": 0, "lng": 181})
    assert resp.status_code == 422


async def test_create_with_location_round_trips(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")

    resp = await api_client.post(
        f"/api/v1/{budget.id}/transactions",
        json={
            "account_id": str(account.id),
            "date": "2026-07-22",
            "amount": "-12.34",
            "latitude": 40.123456,
            "longitude": -75.654321,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["latitude"] == 40.123456
    assert body["longitude"] == -75.654321


async def test_create_rejects_one_sided_location(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")

    resp = await api_client.post(
        f"/api/v1/{budget.id}/transactions",
        json={
            "account_id": str(account.id),
            "date": "2026-07-22",
            "amount": "-12.34",
            "latitude": 40.0,
        },
    )
    assert resp.status_code == 422


async def test_located_transactions_leave_money_math_untouched(api_client, db_session):
    """Coordinates are metadata: the conservation invariants must hold with
    located rows exactly as they do without them."""
    budget, _ = await _seed(db_session, api_client.test_user)
    await assert_financial_invariants(db_session, budget.id)
