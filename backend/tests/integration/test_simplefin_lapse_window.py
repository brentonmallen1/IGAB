"""A lapsed bank link must not walk the sync window past the days it missed.

The report "The Window That Moved On": a bridge's link to one
institution lapsed. It said so (`con.auth`) on every hourly run, and every
one of those runs still stamped the account with its own time. By the time
the link was re-authenticated, the next window (last stamp − 5 days) began a
day after two ordinary $40-scale outflows had posted, so they were never
requested. The ledger then sat exactly their sum off the bank on every run,
and because the account had never been reconciled nothing said so.

Three things follow, each pinned here against the real database:

1. the next window is measured from the bank's own refresh time
   (`balance-date`) when that is earlier than our stamp, so a frozen bridge
   stops advancing it, error or no error;
2. an account a `con.auth` names keeps its stamp, as an orphan does;
3. an exact gap that stands for `PERSISTENT_GAP_RUNS` runs on unreconciled
   bank-fed cash is served as an advisory — and not on a loan.

Figures and names are invented — see the personal-data rule in CLAUDE.md.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from igab.domain.bank_balance import PERSISTENT_GAP_RUNS
from igab.domain.sync_window import SYNC_OVERLAP_DAYS
from igab.integrations.simplefin.client import SimpleFINError
from igab.services.simplefin_service import SimpleFINService

from .factories import (
    create_account,
    create_budget,
    create_simplefin_connection,
    create_user,
    make_services,
)
from .fake_bridge import FakeBridge

ACCT = "ACT-harborstone"
OTHER = "ACT-sapphire"
CONN = "CON-harborstone"
OTHER_CONN = "CON-sapphire"
PATCH_DECRYPT = patch("igab.services.simplefin_service.decrypt", return_value="https://u:p@x.test")


def _ts(on: datetime) -> int:
    return int(on.timestamp())


def bank_txn(txn_id: str, amount: str, on: datetime, *, account: str = ACCT) -> dict:
    return {
        "id": txn_id,
        "account_id": account,
        "amount": amount,
        "payee": "NORTHWIND UTILITIES",
        "description": "NORTHWIND UTILITIES AUTOPAY",
        "posted": _ts(on),
    }


def _service(services, payload, **bridge) -> SimpleFINService:
    svc = SimpleFINService(
        session=services.session,
        repo=services.simplefin_repo,
        account_repo=services.account_repo,
        txn_repo=services.transaction_repo,
        txn_service=services.transactions,
        matching_service=services.matching,
    )
    svc.client = FakeBridge(payload, **bridge)
    return svc


async def _setup(db_session, user=None):
    services = make_services(db_session)
    user = user or await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(
        db_session, budget, "Harborstone Checking", simplefin_account_id=ACCT
    )
    conn = await create_simplefin_connection(db_session, user)
    await db_session.flush()
    return services, budget, account, conn


class TestTheWindowFollowsTheBanksClock:
    async def test_six_stale_runs_then_a_fresh_feed_imports_the_hidden_row(self, db_session):
        """The report's acceptance test. Six runs answered from a refresh frozen
        eight days ago, each stamping its own time; then the bridge recovers
        and reports a $40.00 row posted six days ago — inside the stale
        stretch. Measured from the stamp, the window began five days ago and
        the row was never asked for. Measured from the bank's refresh, it
        imports."""
        services, budget, account, conn = await _setup(db_session)
        now = datetime.now(UTC)
        frozen = now - timedelta(days=8)
        earlier = [bank_txn("old-1", "-12.50", now - timedelta(days=20))]

        with PATCH_DECRYPT:
            for _ in range(6):
                await _service(
                    services,
                    earlier,
                    balances={ACCT: Decimal("-12.50")},
                    balance_dates={ACCT: frozen},
                ).sync(conn.id, budget.id)

        await db_session.refresh(account)
        assert account.last_simplefin_sync_at is not None
        assert account.last_simplefin_sync_at > frozen, "our stamp still moved"

        hidden = bank_txn("hidden-1", "-40.00", now - timedelta(days=6))
        svc = _service(
            services,
            [*earlier, hidden],
            balances={ACCT: Decimal("-52.50")},
            balance_dates={ACCT: now},
            honour_window=True,
        )
        with PATCH_DECRYPT:
            result = await svc.sync(conn.id, budget.id)

        [asked] = svc.client.requests
        assert asked.since is not None
        assert asked.since <= frozen - timedelta(days=SYNC_OVERLAP_DAYS) + timedelta(seconds=1)
        assert result["imported"] == 1, result
        assert result["balance_drift"] == []


class TestALapsedLinkKeepsItsStamp:
    async def test_a_con_auth_run_leaves_the_stamp_unchanged(self, db_session):
        """The run that reports `con.auth` for an institution leaves its
        accounts' stamps where the last real refresh put them, while an
        account on a healthy institution in the same run is stamped as
        usual."""
        services, budget, account, conn = await _setup(db_session)
        other = await create_account(
            db_session, budget, "Sapphire Savings", simplefin_account_id=OTHER
        )
        before = datetime.now(UTC) - timedelta(days=2)
        for acct in (account, other):
            acct.last_simplefin_sync_at = before
            acct.first_sync_complete = True
        await db_session.flush()

        lapse = SimpleFINError(
            code="con.auth",
            message="Harborstone may need attention. Auth required",
            connection_id=CONN,
        )
        with PATCH_DECRYPT:
            result = await _service(
                services,
                [],
                names={ACCT: "HARBORSTONE CHECKING", OTHER: "SAPPHIRE SAVINGS"},
                connections={ACCT: CONN, OTHER: OTHER_CONN},
                errors=[lapse],
            ).sync(conn.id, budget.id)
        assert [e["code"] for e in result["bank_errors"]] == ["con.auth"]

        await db_session.refresh(account)
        await db_session.refresh(other)
        assert account.last_simplefin_sync_at == before
        assert other.last_simplefin_sync_at is not None
        assert other.last_simplefin_sync_at > before

    async def test_the_run_after_re_auth_reaches_back_past_the_lapse(self, db_session):
        """Ten degraded runs, then a clean one: its window starts five days
        before the last real refresh, not five days before the last run."""
        services, budget, account, conn = await _setup(db_session)
        served = datetime.now(UTC) - timedelta(days=3)
        account.last_simplefin_sync_at = served
        account.first_sync_complete = True
        await db_session.flush()

        lapse = SimpleFINError(code="con.auth", message="Auth required", connection_id=CONN)
        with PATCH_DECRYPT:
            for _ in range(10):
                await _service(
                    services,
                    [],
                    names={ACCT: "HARBORSTONE CHECKING"},
                    connections={ACCT: CONN},
                    errors=[lapse],
                ).sync(conn.id, budget.id)
            svc = _service(
                services, [], names={ACCT: "HARBORSTONE CHECKING"}, connections={ACCT: CONN}
            )
            await svc.sync(conn.id, budget.id)

        [asked] = svc.client.requests
        assert asked.since is not None
        assert abs((asked.since - (served - timedelta(days=SYNC_OVERLAP_DAYS))).total_seconds()) < 5


class TestAStandingGapIsAnAdvisory:
    """`bank_drift_persists`, served on the account: an unreconciled bank-fed
    checking account whose ledger has sat exactly $80.00 above the bank for
    the last `PERSISTENT_GAP_RUNS` runs."""

    MISSING = Decimal("80.00")

    async def _standing_gap(self, db_session, api_client, runs: int):
        services, budget, account, conn = await _setup(db_session, api_client.test_user)
        today = date.today()
        rows = [
            bank_txn(
                f"row-{i}",
                "-40.00",
                datetime.combine(today, datetime.min.time(), UTC) - timedelta(days=10 + i),
            )
            for i in range(3)
        ]
        ledger = Decimal("-120.00")
        with PATCH_DECRYPT:
            # The first sync agrees, so no opening anchor absorbs the gap.
            await _service(services, rows, balances={ACCT: ledger}).sync(conn.id, budget.id)
            for _ in range(runs):
                await _service(services, rows, balances={ACCT: ledger - self.MISSING}).sync(
                    conn.id, budget.id
                )
        return budget, account

    async def _served(self, api_client, budget, account) -> list[dict]:
        one = (await api_client.get(f"/api/v1/accounts/{account.id}")).json()
        [listed] = [
            a
            for a in (await api_client.get(f"/api/v1/{budget.id}/accounts")).json()
            if a["id"] == str(account.id)
        ]
        return [one, listed]

    async def test_fires_after_n_identical_gaps(self, db_session, api_client):
        budget, account = await self._standing_gap(db_session, api_client, PERSISTENT_GAP_RUNS)
        for served in await self._served(api_client, budget, account):
            assert served["bank_drift_persists"] is True
            assert served["bank_drift_is_fault"] is False, "an advisory, not a fault"
            assert Decimal(str(served["bank_drift"])) == -self.MISSING

    async def test_not_one_run_short(self, db_session, api_client):
        budget, account = await self._standing_gap(db_session, api_client, PERSISTENT_GAP_RUNS - 1)
        for served in await self._served(api_client, budget, account):
            assert served["bank_drift_persists"] is False

    async def test_not_for_a_loan(self, db_session, api_client):
        """The same six runs, on an account that is a loan: a payoff figure
        drifts daily, so a standing gap there is not evidence of rows."""
        budget, account = await self._standing_gap(db_session, api_client, PERSISTENT_GAP_RUNS)
        account.account_type = "loan"
        await db_session.flush()
        for served in await self._served(api_client, budget, account):
            assert served["bank_drift_persists"] is False

    async def test_every_mutating_path_serves_it(self, db_session, api_client):
        """Required on the response: the edit endpoint judges it afresh."""
        budget, account = await self._standing_gap(db_session, api_client, PERSISTENT_GAP_RUNS)
        edited = await api_client.patch(
            f"/api/v1/accounts/{account.id}", json={"note": "Harborstone everyday"}
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["bank_drift_persists"] is True
        created = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Cascade Checking", "account_type": "checking"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["bank_drift_persists"] is False
