"""Every endpoint that stamps "today" on a figure asks the caller, not the clock.

The server does not know the browser's timezone, so `today_utc()` is already
tomorrow every evening west of UTC. Recording a house value at 7pm on Tuesday
in Seattle dated it Wednesday, and the asset register said Wednesday — the bug
that put `clock.recorded_on` and `ClientDated` here.

Parametrised over all four stamping endpoints because they are near-copies of
each other by their own admission (`assets.py`: "The value endpoints are
near-copies of the liability balance-snapshot ones"), so a fifth one that
forgets should fail here rather than ship a half-migrated rule.

The ranking itself is `tests/unit/test_clock.py`; this file is the wiring.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from igab.repositories.liability_repo import LiabilityRepository
from igab.utils.clock import today_utc

from .factories import create_budget, create_liability

#: A day the server's own clock would never produce, so a stamp matching it
#: proves the caller's date was used rather than coincidentally agreeing.
CALLER_TODAY = today_utc() - timedelta(days=3)


async def _asset_create(api_client, budget, db_session):
    """POST /assets with an opening value — stamps the first value point."""
    resp = await api_client.post(
        f"/api/v1/{budget.id}/assets",
        json={
            "name": "Maple St House",
            "asset_type": "property",
            "value": "250000.00",
            "client_today": CALLER_TODAY.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["value_as_of"]


async def _asset_value(api_client, budget, db_session):
    """POST /assets/{id}/values with no explicit date."""
    created = await api_client.post(
        f"/api/v1/{budget.id}/assets",
        json={"name": "Cedar Wagon", "asset_type": "vehicle"},
    )
    asset_id = created.json()["id"]
    resp = await api_client.post(
        f"/api/v1/{budget.id}/assets/{asset_id}/values",
        json={"value": "18000.00", "client_today": CALLER_TODAY.isoformat()},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["date"]


async def _liability_create(api_client, budget, db_session):
    """POST /liabilities with a manual balance — seeds the snapshot trail.

    Read back through the repository: the seeded snapshot has no GET route,
    and its date is the whole point of the seed.
    """
    resp = await api_client.post(
        f"/api/v1/{budget.id}/liabilities",
        json={
            "name": "Family Loan",
            "liability_type": "personal",
            "interest_rate": "4.5",
            "minimum_payment": "150.00",
            "manual_balance": "3600.00",
            "client_today": CALLER_TODAY.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    snapshots = await LiabilityRepository(db_session).get_snapshots(uuid.UUID(resp.json()["id"]))
    assert len(snapshots) == 1
    return snapshots[0].date.isoformat()


async def _liability_snapshot(api_client, budget, db_session):
    """POST /liabilities/{id}/balance-snapshots with no explicit date."""
    liability = await create_liability(db_session, budget, manual_balance=Decimal("5000.00"))
    resp = await api_client.post(
        f"/api/v1/{budget.id}/liabilities/{liability.id}/balance-snapshots",
        json={"balance": "4750.00", "client_today": CALLER_TODAY.isoformat()},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["date"]


STAMPING_ENDPOINTS = [
    ("asset create", _asset_create),
    ("asset value", _asset_value),
    ("liability create", _liability_create),
    ("liability snapshot", _liability_snapshot),
]


@pytest.mark.parametrize("label,call", STAMPING_ENDPOINTS, ids=[c[0] for c in STAMPING_ENDPOINTS])
async def test_the_callers_today_is_what_gets_stamped(api_client, db_session, label, call):
    budget = await create_budget(db_session, api_client.test_user)
    stamped = await call(api_client, budget, db_session)
    assert stamped == CALLER_TODAY.isoformat(), (
        f"{label} stamped {stamped}, not the caller's {CALLER_TODAY}. This "
        f"endpoint is reading a clock instead of asking clock.recorded_on."
    )


async def test_an_explicit_date_still_outranks_the_callers_today(api_client, db_session):
    """client_today is a default, not an override — a backdated entry stays
    backdated."""
    budget = await create_budget(db_session, api_client.test_user)
    created = await api_client.post(f"/api/v1/{budget.id}/assets", json={"name": "Maple St House"})
    asset_id = created.json()["id"]

    explicit = (today_utc() - timedelta(days=30)).isoformat()
    resp = await api_client.post(
        f"/api/v1/{budget.id}/assets/{asset_id}/values",
        json={
            "value": "240000.00",
            "date": explicit,
            "client_today": CALLER_TODAY.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["date"] == explicit


async def test_a_caller_that_sends_nothing_still_gets_a_date(api_client, db_session):
    """The fallback stays: a script or curl caller outside the browser has no
    better answer than the server's clock, and must not be refused."""
    budget = await create_budget(db_session, api_client.test_user)
    resp = await api_client.post(
        f"/api/v1/{budget.id}/assets",
        json={"name": "Cascade Point HYSA", "value": "1000.00"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["value_as_of"] == today_utc().isoformat()
