"""The sync log's endpoints, and the health check that badges the nav.

The route order matters here: `/sync-runs/health` is declared before
`/sync-runs/{run_id}`, because FastAPI matches in declaration order and would
otherwise try to parse "health" as a UUID.
"""

import pytest

from igab.db.models import Budget, SyncRun, SyncRunAccount

from .factories import create_budget


async def _budget(api_client, db_session) -> Budget:
    """A budget the overridden test user owns, so BudgetAccess admits it."""
    budget = await create_budget(db_session, api_client.test_user)
    await db_session.flush()
    return budget


async def _add_run(db_session, budget, **over) -> SyncRun:
    fields = {
        "budget_id": budget.id,
        "trigger": "global",
        "status": "ok",
        "feed_txn_count": 4,
        "imported": 2,
        "skipped": 2,
        "skip_reasons": {"already_posted": 2},
        "bank_errors": [],
        "orphaned_links": [],
    }
    fields.update(over)
    run = SyncRun(**fields)
    db_session.add(run)
    await db_session.flush()
    return run


ORPHAN = {
    "account_id": "00000000-0000-0000-0000-000000000001",
    "account_name": "Harborstone Checking",
    "stored_simplefin_id": "ACT-retired",
    "suggested_feed_id": "ACT-current",
    "suggested_feed_name": "HARBORSTONE EVERYDAY CHECKING",
}


class TestSyncRunList:
    @pytest.mark.asyncio
    async def test_runs_come_back_newest_first(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        await _add_run(db_session, budget, imported=1)
        await _add_run(db_session, budget, imported=9)
        await db_session.commit()

        resp = await api_client.get(f"/api/v1/{budget.id}/simplefin/sync-runs")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 2
        # Both rows share a transaction timestamp, so this only holds because
        # ordering is by the identity `seq`.
        assert body["runs"][0]["imported"] == 9

    @pytest.mark.asyncio
    async def test_a_run_carries_its_skip_reasons(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        await _add_run(db_session, budget, skip_reasons={"foreign_account": 586})
        await db_session.commit()

        resp = await api_client.get(f"/api/v1/{budget.id}/simplefin/sync-runs")
        assert resp.json()["runs"][0]["skip_reasons"] == {"foreign_account": 586}


class TestSyncRunDetail:
    @pytest.mark.asyncio
    async def test_detail_carries_per_account_rows(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        run = await _add_run(db_session, budget)
        db_session.add(
            SyncRunAccount(
                sync_run_id=run.id,
                account_name="Harborstone Checking",
                simplefin_account_id="ACT-retired",
                feed_txn_count=0,
                orphaned=True,
            )
        )
        await db_session.commit()

        resp = await api_client.get(f"/api/v1/{budget.id}/simplefin/sync-runs/{run.id}")
        assert resp.status_code == 200, resp.text
        [account] = resp.json()["accounts"]
        assert account["account_name"] == "Harborstone Checking"
        assert account["feed_txn_count"] == 0
        assert account["orphaned"] is True

    @pytest.mark.asyncio
    async def test_a_run_from_another_budget_is_not_found(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        run = await _add_run(db_session, budget, budget_id=None)
        await db_session.commit()

        resp = await api_client.get(f"/api/v1/{budget.id}/simplefin/sync-runs/{run.id}")
        assert resp.status_code == 404


class TestSyncHealth:
    @pytest.mark.asyncio
    async def test_health_is_clean_with_no_runs(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        resp = await api_client.get(f"/api/v1/{budget.id}/simplefin/sync-runs/health")
        assert resp.status_code == 200, resp.text
        assert resp.json()["orphaned_links"] == []
        assert resp.json()["last_run_at"] is None

    @pytest.mark.asyncio
    async def test_health_reports_an_orphaned_link(self, api_client, db_session):
        budget = await _budget(api_client, db_session)
        await _add_run(db_session, budget, status="degraded", orphaned_links=[ORPHAN])
        await db_session.commit()

        resp = await api_client.get(f"/api/v1/{budget.id}/simplefin/sync-runs/health")
        body = resp.json()
        assert body["orphaned_links"][0]["account_name"] == "Harborstone Checking"
        assert body["orphaned_links"][0]["suggested_feed_id"] == "ACT-current"

    @pytest.mark.asyncio
    async def test_a_fixed_link_clears_the_badge(self, api_client, db_session):
        """Health reads the latest run, not the latest problem. A finding that
        outlives its fix is how a badge becomes noise people scroll past."""
        budget = await _budget(api_client, db_session)
        await _add_run(db_session, budget, status="degraded", orphaned_links=[ORPHAN])
        await _add_run(db_session, budget, status="ok")
        await db_session.commit()

        resp = await api_client.get(f"/api/v1/{budget.id}/simplefin/sync-runs/health")
        assert resp.json()["orphaned_links"] == []

    @pytest.mark.asyncio
    async def test_health_surfaces_only_auth_errors(self, api_client, db_session):
        """`gen.api` (the capped-range notice) is ours to fix, not the user's."""
        budget = await _budget(api_client, db_session)
        await _add_run(
            db_session,
            budget,
            bank_errors=[
                {"code": "gen.api", "message": "range capped", "connection_id": None},
                {"code": "con.auth", "message": "Auth required", "connection_id": "MBR-1"},
            ],
        )
        await db_session.commit()

        body = (await api_client.get(f"/api/v1/{budget.id}/simplefin/sync-runs/health")).json()
        assert [e["code"] for e in body["needs_auth"]] == ["con.auth"]
