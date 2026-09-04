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
    async def test_it_names_the_categories_it_tagged(self, api_client):
        """A count cannot answer "show me what you did"."""
        body = await _import(api_client)
        budget_id = body["budget"]["id"]

        stored = (await api_client.get(f"/api/v1/{budget_id}/import-summary")).json()["summary"]
        tagged = stored["tagged_categories"]

        assert stored["categories_tagged"] == len(tagged)
        by_key = {t["system_key"]: t for t in tagged}
        assert "savings" in by_key
        # And why. "Emergency Fund" sits in a group called "Savings" and both
        # names point at the same key -- the category's own wins, which is the
        # precedence that makes a "Savings" category inside "True Expenses"
        # savings rather than a long-term expense.
        assert by_key["savings"]["matched_on"] == "Emergency Fund"
        assert uuid.UUID(by_key["savings"]["category_id"])

    @pytest.mark.asyncio
    async def test_a_budget_that_was_never_imported_reports_nothing(self, api_client, db_session):
        """An ordinary case, not an error: the review still opens."""
        budget = await create_budget(db_session, api_client.test_user)
        await db_session.flush()

        resp = await api_client.get(f"/api/v1/{budget.id}/import-summary")
        assert resp.status_code == 200
        assert resp.json() == {"summary": None, "reviewed_at": None}


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
