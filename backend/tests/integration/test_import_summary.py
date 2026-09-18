"""What an import decided, kept where it can be looked at again.

The summary used to exist only as a stack of up to six toasts fired while the
app was changing route. None of it -- the parity check, which plan rows were
skipped, which categories were tagged, up to fifty per-row errors of which the
UI showed one -- is recoverable from the resulting budget.
"""

import io
import uuid
import zipfile

import pytest

from .factories import create_budget, create_user

REGISTER = """Account,Date,Payee,Category Group,Category,Memo,Outflow,Inflow,Cleared
Checking,07/01/2026,Employer,Inflow,Ready to Assign,,,"2,000.00",Cleared
Checking,07/02/2026,Corner Market,Everyday,Groceries,,60.00,,Cleared
Checking,07/03/2026,Bank,Savings,Emergency Fund,,100.00,,Cleared
Checking,07/04/2026,Streaming Co,Everyday,Amazon Prime,,15.00,,Cleared
"""


def _ynab_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("My Budget - Register.csv", REGISTER)
    return buf.getvalue()


async def _import(api_client, name="Imported"):
    resp = await api_client.post(
        "/api/v1/budgets/import-ynab",
        files={"file": ("export.zip", _ynab_zip(), "application/zip")},
        data={"name": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestItSurvivesTheRequest:
    @pytest.mark.asyncio
    async def test_the_summary_round_trips(self, api_client):
        body = await _import(api_client)
        budget_id = body["budget"]["id"]

        resp = await api_client.get(f"/api/v1/{budget_id}/import-summary")
        assert resp.status_code == 200, resp.text
        stored = resp.json()["summary"]

        # The same figures the response carried, not a re-derivation.
        assert stored["transactions"] == body["import_result"]["transactions"]
        assert stored["accounts"] == body["import_result"]["accounts"]
        assert stored["categories"] == body["import_result"]["categories"]
        assert stored["category_groups"] == body["import_result"]["category_groups"]
        # A register-only export cannot anchor, and the summary says so
        # rather than staying silent (the review dialog reads this).
        assert stored["anchored_at"] is None
        assert stored["anchor_skipped_reason"] == "no plan in the export"

    @pytest.mark.asyncio
    async def test_it_tags_nothing_and_still_serves_the_fields(self, api_client):
        """An import writes no tags now — "Emergency Fund" is suggested in the
        review, not tagged. The fields stay, so a summary stored by an import
        that did tag still renders what it did."""
        body = await _import(api_client)
        budget_id = body["budget"]["id"]

        stored = (await api_client.get(f"/api/v1/{budget_id}/import-summary")).json()["summary"]

        assert stored["categories_tagged"] == 0
        assert stored["tagged_categories"] == []
        suggestions = (await api_client.get(f"/api/v1/{budget_id}/tags/suggestions")).json()
        assert ("emergency_fund", "Emergency Fund") in {
            (s["system_key"], s["matched_on"]) for s in suggestions
        }

    @pytest.mark.asyncio
    async def test_a_budget_that_was_never_imported_reports_nothing(self, api_client, db_session):
        """An ordinary case, not an error: the review still opens."""
        budget = await create_budget(db_session, api_client.test_user)
        await db_session.flush()

        resp = await api_client.get(f"/api/v1/{budget.id}/import-summary")
        assert resp.status_code == 200
        assert resp.json() == {
            "summary": None,
            "reviewed_at": None,
            "liabilities_needing_terms": [],
        }


class TestSeenOnce:
    @pytest.mark.asyncio
    async def test_it_starts_unreviewed(self, api_client):
        body = await _import(api_client)
        resp = await api_client.get(f"/api/v1/{body['budget']['id']}/import-summary")
        assert resp.json()["reviewed_at"] is None

    @pytest.mark.asyncio
    async def test_marking_it_stamps_the_time(self, api_client):
        body = await _import(api_client)
        budget_id = body["budget"]["id"]

        assert (
            await api_client.post(f"/api/v1/{budget_id}/import-summary/reviewed")
        ).status_code == 204

        after = (await api_client.get(f"/api/v1/{budget_id}/import-summary")).json()
        assert after["reviewed_at"] is not None
        # Stamping does not consume the summary -- the review stays reachable.
        assert after["summary"] is not None

    @pytest.mark.asyncio
    async def test_marking_twice_is_harmless(self, api_client):
        body = await _import(api_client)
        budget_id = body["budget"]["id"]
        for _ in range(2):
            resp = await api_client.post(f"/api/v1/{budget_id}/import-summary/reviewed")
            assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_another_users_budget_is_not_readable(self, api_client, db_session):
        other = await create_user(db_session, email="someone@else.test")
        budget = await create_budget(db_session, other)
        await db_session.flush()

        resp = await api_client.get(f"/api/v1/{budget.id}/import-summary")
        assert resp.status_code in (403, 404)


class TestHeldOutRows:
    @pytest.mark.asyncio
    async def test_held_out_future_defaults_to_empty_on_a_pre_feature_summary(
        self, api_client, db_session
    ):
        """Stored summaries are re-validated on read; one written before
        future rows were held out carries no such field and must still load."""
        from sqlalchemy import select, update

        from igab.db.models import Budget

        body = await _import(api_client)
        budget_id = body["budget"]["id"]
        stored = (
            await db_session.execute(select(Budget).where(Budget.id == uuid.UUID(budget_id)))
        ).scalar_one()
        old = {k: v for k, v in stored.import_summary.items() if not k.startswith("held_out")}
        await db_session.execute(
            update(Budget).where(Budget.id == uuid.UUID(budget_id)).values(import_summary=old)
        )
        await db_session.commit()

        resp = await api_client.get(f"/api/v1/{budget_id}/import-summary")
        assert resp.status_code == 200, resp.text
        summary = resp.json()["summary"]
        assert summary["held_out_future"] == []
        assert summary["held_out_splits_uncategorized"] == 0


class TestLoansWithoutTerms:
    """A YNAB export carries no account metadata — no rate, no minimum
    payment, no payoff date — so every liability arrives inert. The review is
    where the user is asked, because nothing else in the app knows an import
    just happened.
    """

    @pytest.mark.asyncio
    async def test_a_loan_without_a_rate_is_named(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        made = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Harborstone Auto Loan", "account_type": "loan", "on_budget": False},
        )
        assert made.status_code == 201, made.text

        resp = await api_client.get(f"/api/v1/{budget.id}/import-summary")
        named = resp.json()["liabilities_needing_terms"]
        assert [row["name"] for row in named] == ["Harborstone Auto Loan"]
        assert named[0]["account_id"] == made.json()["id"]

    @pytest.mark.asyncio
    async def test_it_disappears_once_the_rate_is_filled_in(self, api_client, db_session):
        """Queried live rather than recorded at import time, so answering the
        question is what clears it — no second flag to keep in step."""
        budget = await create_budget(db_session, api_client.test_user)
        await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Harborstone Auto Loan", "account_type": "loan", "on_budget": False},
        )
        listed = await api_client.get(f"/api/v1/{budget.id}/liabilities")
        liability_id = listed.json()[0]["id"]
        patched = await api_client.patch(
            f"/api/v1/{budget.id}/liabilities/{liability_id}", json={"interest_rate": "6.125"}
        )
        assert patched.status_code == 200, patched.text

        resp = await api_client.get(f"/api/v1/{budget.id}/import-summary")
        assert resp.json()["liabilities_needing_terms"] == []
