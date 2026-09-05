"""The changes page carries names for the ids its snapshots hold.

A snapshot stores bare references — account_id, payee_id, _tag_ids — and
the Activity page has to say "Harborstone Market · Checking", not a UUID.
Resolution happens server-side because the client is genuinely missing the
input: a row can point at something deleted since, whose name appears on no
list endpoint. One `names` map per page; the client looks up what it shows.
"""

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_tag,
)


class TestChangesNames:
    async def test_transaction_rows_resolve_account_and_payee(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        account = await create_account(db_session, budget, name="Everyday Checking")
        payee = await create_payee(db_session, budget, name="Harborstone Market")
        await db_session.commit()

        r = await api_client.post(
            f"/api/v1/{budget.id}/transactions",
            json={
                "account_id": str(account.id),
                "date": "2026-09-04",
                "amount": "-42.50",
                "payee_id": str(payee.id),
            },
        )
        assert r.status_code == 201, r.text

        body = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()
        assert body["names"][str(account.id)] == "Everyday Checking"
        assert body["names"][str(payee.id)] == "Harborstone Market"

    async def test_a_deleted_payee_still_names_itself(self, db_session, api_client):
        """The whole reason resolution is server-side: after the payee is
        deleted, no list endpoint serves its name — but its rows in the feed
        must keep saying who they were about."""
        budget = await create_budget(db_session, api_client.test_user)
        account = await create_account(db_session, budget)
        payee = await create_payee(db_session, budget, name="Closed Corner Store")
        await db_session.commit()

        # A recorded row that references the payee…
        r = await api_client.post(
            f"/api/v1/{budget.id}/transactions",
            json={
                "account_id": str(account.id),
                "date": "2026-09-01",
                "amount": "-12.00",
                "payee_id": str(payee.id),
            },
        )
        assert r.status_code == 201, r.text
        # …then the payee itself goes away.
        r = await api_client.delete(f"/api/v1/payees/{payee.id}")
        assert r.status_code in (200, 204), r.text

        body = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()
        assert body["names"][str(payee.id)] == "Closed Corner Store"

    async def test_tag_membership_ids_resolve(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        group = await create_category_group(db_session, budget)
        category = await create_category(db_session, budget, group, name="Groceries")
        tag = await create_tag(db_session, budget, name="Essential")
        await db_session.commit()

        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/{category.id}/tags",
            json={"tag_ids": [str(tag.id)]},
        )
        assert r.status_code == 200, r.text

        body = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()
        assert body["names"][str(tag.id)] == "Essential"
