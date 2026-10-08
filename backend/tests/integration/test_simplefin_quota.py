"""What each sync asks the bridge, and which quota pays for it.

SimpleFIN keeps "requests for all accounts" and "requests for individual
accounts" (`GET /accounts?account=...`) on separate quotas. IGAB counted the
two separately and never sent `account=`: every per-account Sync and every
"Refetch 90 days" downloaded every account and filtered in Python, so both of
IGAB's counters drew on the bridge's one all-accounts quota.

The rule now: one account asked for → `account=` that account, charged to the
account bucket; everything → no filter, charged to the global bucket. These
tests assert on the request the bridge received, one per entry path, because
a result can look right while the request behind it drew on the wrong quota.
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from igab.domain.sync_window import SIMPLEFIN_MAX_WINDOW_DAYS
from igab.integrations.simplefin.limits import ACCOUNT_DAILY_LIMIT, GLOBAL_DAILY_LIMIT
from igab.services.simplefin_service import SimpleFINService
from igab.utils.clock import today_utc

from .factories import (
    create_account,
    create_budget,
    create_simplefin_connection,
    create_user,
    make_services,
)
from .fake_bridge import FakeBridge

SAPPHIRE = "ACT-sapphire"
HARBORSTONE = "ACT-harborstone"
#: The id the bridge reissues Sapphire under, carrying the same bank name.
SAPPHIRE_REISSUED = "ACT-sapphire-2"
SAPPHIRE_BANK_NAME = "SAPPHIRE VISA SIGNATURE"

PATCH_DECRYPT = patch("igab.services.simplefin_service.decrypt", return_value="https://u:p@x.test")


def _ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 12, tzinfo=UTC).timestamp())


def bank_txn(txn_id: str, amount: str, on: date, *, account: str) -> dict:
    return {
        "id": txn_id,
        "account_id": account,
        "amount": amount,
        "payee": "CORNER MARKET",
        "description": "CORNER MARKET POS PURCHASE",
        "posted": _ts(on),
    }


def _payload(sapphire_id: str = SAPPHIRE) -> list[dict]:
    day = date.today() - timedelta(days=3)
    return [
        bank_txn("s-1", "-42.00", day, account=sapphire_id),
        bank_txn("h-1", "-18.00", day, account=HARBORSTONE),
    ]


def _bridge(sapphire_id: str = SAPPHIRE) -> FakeBridge:
    return FakeBridge(
        _payload(sapphire_id),
        names={sapphire_id: SAPPHIRE_BANK_NAME, HARBORSTONE: "HARBORSTONE EVERYDAY CHECKING"},
    )


def _service(services, bridge: FakeBridge) -> SimpleFINService:
    svc = SimpleFINService(
        session=services.session,
        repo=services.simplefin_repo,
        account_repo=services.account_repo,
        txn_repo=services.transaction_repo,
        txn_service=services.transactions,
        matching_service=services.matching,
    )
    svc.client = bridge
    return svc


async def _setup(db_session, user=None):
    services = make_services(db_session)
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    sapphire = await create_account(
        db_session, budget, "Sapphire Visa", simplefin_account_id=SAPPHIRE
    )
    sapphire.simplefin_account_name = SAPPHIRE_BANK_NAME
    harborstone = await create_account(
        db_session, budget, "Harborstone Checking", simplefin_account_id=HARBORSTONE
    )
    conn = await create_simplefin_connection(db_session, user)
    await db_session.flush()
    return services, budget, sapphire, harborstone, conn


async def _counters(db_session, conn) -> tuple[int, int]:
    """(global, account) requests counted today."""
    await db_session.refresh(conn)
    if conn.last_request_date != today_utc():
        return 0, 0
    return conn.global_requests_today, conn.account_requests_today


# ── One test per entry path ──────────────────────────────────────────────────


async def test_a_per_account_sync_names_that_account(db_session):
    services, budget, sapphire, _, conn = await _setup(db_session)
    bridge = _bridge()

    with PATCH_DECRYPT:
        result = await _service(services, bridge).sync(
            conn.id, budget.id, account_simplefin_id=SAPPHIRE
        )

    assert result.get("error") is None, result
    assert bridge.filters == [(SAPPHIRE,)], "exactly one request, naming exactly one account"
    assert result["imported"] == 1
    assert await _counters(db_session, conn) == (0, 1), "charged to the account bucket only"


async def test_a_connection_sync_with_no_account_asks_for_everything(db_session):
    services, budget, _, _, conn = await _setup(db_session)
    bridge = _bridge()

    with PATCH_DECRYPT:
        result = await _service(services, bridge).sync(conn.id, budget.id)

    assert result.get("error") is None, result
    assert bridge.filters == [None]
    assert result["imported"] == 2
    assert await _counters(db_session, conn) == (1, 0)


async def test_sync_all_asks_for_everything(db_session):
    services, budget, _, _, conn = await _setup(db_session)
    bridge = _bridge()

    with PATCH_DECRYPT:
        result = await _service(services, bridge).sync_all(conn.user_id, budget.id)

    assert result["connections"][0]["error"] is None, result
    assert bridge.filters == [None]
    assert await _counters(db_session, conn) == (1, 0)


async def test_a_global_sync_with_an_account_switched_off_still_asks_for_everything(db_session):
    """Filtering to the accounts whose sync is on would move every scheduled
    run onto the per-account quota, and hide a reissued id from the link
    audit — which finds the account's new id by name across the whole feed."""
    services, budget, _, harborstone, conn = await _setup(db_session)
    harborstone.simplefin_sync_enabled = False
    await db_session.flush()
    bridge = _bridge()

    with PATCH_DECRYPT:
        result = await _service(services, bridge).sync(conn.id, budget.id)

    assert bridge.filters == [None]
    assert result["imported"] == 1, "the switched-off account still imports nothing"
    assert await _counters(db_session, conn) == (1, 0)


async def test_the_hourly_job_asks_for_everything(db_session):
    """Through the real job: it builds its own service, so the bridge is
    swapped in where the service makes its client."""
    from .test_sync_schedule import _session_factory

    services, budget, _, _, conn = await _setup(db_session)
    conn.sync_hours = [9]
    await db_session.flush()
    bridge = _bridge()

    from igab.tasks.scheduler import process_auto_simplefin_sync

    with (
        PATCH_DECRYPT,
        patch("igab.db.session.AsyncSessionLocal", _session_factory(db_session)),
        patch("igab.services.simplefin_service.SimpleFINClient", return_value=bridge),
        patch("igab.tasks.scheduler.datetime") as clock,
    ):
        clock.now.return_value = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)
        await process_auto_simplefin_sync()

    assert bridge.filters == [None]
    assert await _counters(db_session, conn) == (1, 0)


# ── Through the API: the wiring from request to client ───────────────────────


async def _api_setup(db_session, api_client, bridge: FakeBridge):
    from igab.dependencies import get_simplefin_service
    from igab.main import app

    services, budget, sapphire, harborstone, conn = await _setup(
        db_session, user=api_client.test_user
    )
    svc = _service(services, bridge)
    app.dependency_overrides[get_simplefin_service] = lambda: svc
    return budget, sapphire, conn


async def test_the_sync_endpoint_passes_the_account_through_to_the_request(db_session, api_client):
    bridge = _bridge()
    budget, _, conn = await _api_setup(db_session, api_client, bridge)

    with PATCH_DECRYPT:
        r = await api_client.post(
            f"/api/v1/simplefin/connections/{conn.id}/sync",
            params={"budget_id": str(budget.id), "account_simplefin_id": SAPPHIRE},
        )
    assert r.status_code == 200, r.text
    assert bridge.filters == [(SAPPHIRE,)]
    assert r.json()["account_used"] == 1
    assert r.json()["global_used"] == 0


async def test_the_sync_endpoint_without_an_account_asks_for_everything(db_session, api_client):
    bridge = _bridge()
    budget, _, conn = await _api_setup(db_session, api_client, bridge)

    with PATCH_DECRYPT:
        r = await api_client.post(
            f"/api/v1/simplefin/connections/{conn.id}/sync", params={"budget_id": str(budget.id)}
        )
    assert r.status_code == 200, r.text
    assert bridge.filters == [None]


async def test_refetch_names_the_account_and_reaches_back_the_full_window(db_session, api_client):
    bridge = _bridge()
    budget, sapphire, conn = await _api_setup(db_session, api_client, bridge)
    sapphire.last_simplefin_sync_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    with PATCH_DECRYPT:
        r = await api_client.post(
            f"/api/v1/accounts/{sapphire.id}/simplefin-refetch",
            json={"connection_id": str(conn.id)},
        )
    assert r.status_code == 200, r.text
    [request] = bridge.requests
    assert request.account_ids == (SAPPHIRE,)
    floor = datetime.now(UTC) - timedelta(days=SIMPLEFIN_MAX_WINDOW_DAYS)
    assert request.since is not None
    assert abs((request.since - floor).total_seconds()) < 60, "start-date rides with the filter"
    assert await _counters(db_session, conn) == (0, 1)


# ── A per-account sync whose id the bank reissued ────────────────────────────


async def test_a_missing_account_looks_at_the_whole_feed_once_and_relinks(db_session):
    """The filtered answer cannot carry the account's new id — it was asked
    for the old one. One all-accounts request finds it by name, charged to
    the all-accounts quota, and the run relinks and imports in one go."""
    services, budget, sapphire, _, conn = await _setup(db_session)
    # Never synced, so the first request already reaches back the full window
    # and the relink needs no wider one.
    bridge = _bridge(sapphire_id=SAPPHIRE_REISSUED)

    with PATCH_DECRYPT:
        result = await _service(services, bridge).sync(
            conn.id, budget.id, account_simplefin_id=SAPPHIRE
        )

    assert bridge.filters == [(SAPPHIRE,), None], "filtered, then once unfiltered"
    await db_session.refresh(sapphire)
    assert sapphire.simplefin_account_id == SAPPHIRE_REISSUED, "relinked by its exact name"
    assert result["orphaned_links"] == []
    assert result["imported"] == 1
    assert result["skip_reasons"].get("foreign_account") == 1, "Harborstone was not filed"
    assert result["bank_errors"] == [], "the filtered answer's act.failed went with it"
    assert await _counters(db_session, conn) == (1, 1), "one request from each bucket"


async def test_a_relink_refetch_in_an_account_run_names_the_new_id(db_session):
    """When the relinked account is owed a wider window, the wider request is
    the account run's own: it names the id the account now has, on the
    account quota."""
    services, budget, sapphire, _, conn = await _setup(db_session)
    # Served an hour ago, as far as its stamp knows: the first request asks
    # for the last few days only.
    sapphire.first_sync_complete = True
    sapphire.last_simplefin_sync_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()
    bridge = _bridge(sapphire_id=SAPPHIRE_REISSUED)

    with PATCH_DECRYPT:
        await _service(services, bridge).sync(conn.id, budget.id, account_simplefin_id=SAPPHIRE)

    assert bridge.filters == [(SAPPHIRE,), None, (SAPPHIRE_REISSUED,)]
    floor = datetime.now(UTC) - timedelta(days=SIMPLEFIN_MAX_WINDOW_DAYS)
    assert bridge.requests[2].since is not None
    assert abs((bridge.requests[2].since - floor).total_seconds()) < 60
    assert await _counters(db_session, conn) == (1, 2)


async def test_no_lookup_when_the_all_accounts_quota_is_spent(db_session):
    """No second request: the run reports the orphan exactly as it did before
    the lookup existed, and the account quota pays only for its own."""
    services, budget, sapphire, _, conn = await _setup(db_session)
    conn.last_request_date = today_utc()
    conn.global_requests_today = GLOBAL_DAILY_LIMIT
    await db_session.flush()
    bridge = _bridge(sapphire_id=SAPPHIRE_REISSUED)

    with PATCH_DECRYPT:
        result = await _service(services, bridge).sync(
            conn.id, budget.id, account_simplefin_id=SAPPHIRE
        )

    assert bridge.filters == [(SAPPHIRE,)]
    [orphan] = result["orphaned_links"]
    assert orphan["account_name"] == "Sapphire Visa"
    # The bridge's own word for it stays on the run, beside the orphan.
    assert [e["code"] for e in result["bank_errors"]] == ["act.failed"]
    await db_session.refresh(sapphire)
    assert sapphire.simplefin_account_id == SAPPHIRE, "nothing to relink it to"
    assert await _counters(db_session, conn) == (GLOBAL_DAILY_LIMIT, 1)


async def test_a_global_sync_never_needs_the_lookup(db_session):
    """The whole feed is already in hand: a reissued id costs nothing extra."""
    services, budget, sapphire, _, conn = await _setup(db_session)
    bridge = _bridge(sapphire_id=SAPPHIRE_REISSUED)

    with PATCH_DECRYPT:
        await _service(services, bridge).sync(conn.id, budget.id)

    assert bridge.filters == [None]
    await db_session.refresh(sapphire)
    assert sapphire.simplefin_account_id == SAPPHIRE_REISSUED
    assert await _counters(db_session, conn) == (1, 0)


# ── The account listing ──────────────────────────────────────────────────────


async def test_listing_the_banks_accounts_counts_against_the_global_quota(db_session, api_client):
    bridge = _bridge()
    _, _, conn = await _api_setup(db_session, api_client, bridge)

    with PATCH_DECRYPT:
        r = await api_client.get(f"/api/v1/simplefin/connections/{conn.id}/accounts")

    assert r.status_code == 200, r.text
    assert {a["id"] for a in r.json()} == {SAPPHIRE, HARBORSTONE}
    assert bridge.listings == 1
    assert await _counters(db_session, conn) == (1, 0)


async def test_listing_is_refused_at_the_limit_with_the_reset_named(db_session, api_client):
    bridge = _bridge()
    _, _, conn = await _api_setup(db_session, api_client, bridge)
    conn.last_request_date = today_utc()
    conn.global_requests_today = GLOBAL_DAILY_LIMIT
    await db_session.flush()

    with PATCH_DECRYPT:
        r = await api_client.get(f"/api/v1/simplefin/connections/{conn.id}/accounts")

    assert r.status_code == 429, r.text
    assert "midnight UTC" in r.json()["detail"]
    assert 0 <= int(r.headers["Retry-After"]) <= 24 * 3600
    assert bridge.listings == 0, "refused before the bridge is asked"
    assert await _counters(db_session, conn) == (GLOBAL_DAILY_LIMIT, 0)


async def test_a_listing_the_bridge_fails_still_counts(db_session, api_client):
    import httpx

    class Refusing(FakeBridge):
        async def get_accounts(self, access_url: str) -> list[dict]:
            self.listings += 1
            raise httpx.ConnectError("bridge unreachable")

    bridge = Refusing()
    _, _, conn = await _api_setup(db_session, api_client, bridge)

    with PATCH_DECRYPT:
        r = await api_client.get(f"/api/v1/simplefin/connections/{conn.id}/accounts")

    assert r.status_code == 502, r.text
    assert "SimpleFIN" in r.json()["detail"]
    assert await _counters(db_session, conn) == (1, 0)


# ── The status the client draws ──────────────────────────────────────────────


async def test_status_serves_the_limits(db_session, api_client):
    _, _, conn = await _api_setup(db_session, api_client, _bridge())

    r = await api_client.get(f"/api/v1/simplefin/connections/{conn.id}/status")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["global_limit"] == GLOBAL_DAILY_LIMIT
    assert body["account_limit"] == ACCOUNT_DAILY_LIMIT
