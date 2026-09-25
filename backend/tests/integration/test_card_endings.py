"""Card endings: the last four digits of each card that pays from an account.

Full CRUD from the account's settings, visible to ⌘Z, unique per budget —
and served on each AI job as the account whose card paid, as of now.
"""

import uuid

from igab.db.models import AIJob

from .factories import create_account, create_budget


async def _setup(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    sapphire = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    harborstone = await create_account(db_session, budget, "Harborstone Checking")
    await db_session.commit()
    return budget, sapphire, harborstone


async def _endings(api_client, budget):
    r = await api_client.get(f"/api/v1/{budget.id}/card-endings")
    assert r.status_code == 200, r.text
    return r.json()


async def _add(api_client, budget, account, last4, label=None):
    return await api_client.post(
        f"/api/v1/{budget.id}/card-endings",
        json={"account_id": str(account.id), "last4": last4, "label": label},
    )


class TestCrud:
    async def test_one_account_holds_several_cards(self, db_session, api_client):
        budget, sapphire, _ = await _setup(db_session, api_client)
        for last4, label in (("4417", "Jane's card"), ("9021", "Apple Pay"), ("3308", None)):
            r = await _add(api_client, budget, sapphire, last4, label)
            assert r.status_code == 201, r.text
        endings = await _endings(api_client, budget)
        assert [(e["last4"], e["label"]) for e in endings] == [
            ("3308", None),
            ("4417", "Jane's card"),
            ("9021", "Apple Pay"),
        ]
        assert {e["account_id"] for e in endings} == {str(sapphire.id)}

    async def test_an_ending_names_one_account(self, db_session, api_client):
        budget, sapphire, harborstone = await _setup(db_session, api_client)
        assert (await _add(api_client, budget, sapphire, "4417")).status_code == 201
        r = await _add(api_client, budget, harborstone, "4417")
        assert r.status_code == 409
        assert "Sapphire Visa" in r.json()["detail"]

    async def test_only_four_digits_are_an_ending(self, db_session, api_client):
        budget, sapphire, _ = await _setup(db_session, api_client)
        for bad in ("441", "44171", "44a7", "", "4 17"):
            assert (await _add(api_client, budget, sapphire, bad)).status_code == 422, bad

    async def test_edit_moves_relabels_and_renumbers(self, db_session, api_client):
        budget, sapphire, harborstone = await _setup(db_session, api_client)
        ending = (await _add(api_client, budget, sapphire, "4417", "Old card")).json()
        r = await api_client.patch(
            f"/api/v1/{budget.id}/card-endings/{ending['id']}",
            json={"account_id": str(harborstone.id), "last4": "5520", "label": "  "},
        )
        assert r.status_code == 200, r.text
        assert (r.json()["account_id"], r.json()["last4"], r.json()["label"]) == (
            str(harborstone.id),
            "5520",
            None,
        )

    async def test_renumbering_onto_a_taken_ending_is_refused(self, db_session, api_client):
        budget, sapphire, harborstone = await _setup(db_session, api_client)
        await _add(api_client, budget, sapphire, "4417")
        other = (await _add(api_client, budget, harborstone, "5520")).json()
        r = await api_client.patch(
            f"/api/v1/{budget.id}/card-endings/{other['id']}", json={"last4": "4417"}
        )
        assert r.status_code == 409

    async def test_an_account_from_another_budget_is_not_found(self, db_session, api_client):
        budget, _, _ = await _setup(db_session, api_client)
        other_budget = await create_budget(db_session, api_client.test_user)
        stranger = await create_account(db_session, other_budget, "Elsewhere")
        await db_session.commit()
        assert (await _add(api_client, budget, stranger, "4417")).status_code == 404

    async def test_delete(self, db_session, api_client):
        budget, sapphire, _ = await _setup(db_session, api_client)
        ending = (await _add(api_client, budget, sapphire, "4417")).json()
        r = await api_client.delete(f"/api/v1/{budget.id}/card-endings/{ending['id']}")
        assert r.status_code == 204
        assert await _endings(api_client, budget) == []


class TestUndo:
    async def _undo(self, api_client, budget):
        r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert r.status_code == 200, r.text
        return r.json()

    async def test_create_update_and_delete_each_undo(self, db_session, api_client):
        budget, sapphire, _ = await _setup(db_session, api_client)
        ending = (await _add(api_client, budget, sapphire, "4417", "Jane's card")).json()
        await api_client.patch(
            f"/api/v1/{budget.id}/card-endings/{ending['id']}", json={"label": "Apple Pay"}
        )
        await api_client.delete(f"/api/v1/{budget.id}/card-endings/{ending['id']}")

        undone = await self._undo(api_client, budget)
        assert (undone["entity_type"], undone["action"]) == ("card_ending", "delete")
        [back] = await _endings(api_client, budget)
        assert (back["id"], back["label"]) == (ending["id"], "Apple Pay")

        await self._undo(api_client, budget)
        [back] = await _endings(api_client, budget)
        assert back["label"] == "Jane's card"

        await self._undo(api_client, budget)
        assert await _endings(api_client, budget) == []


class TestServedOnTheJob:
    async def _job(self, db_session, budget, account, last4):
        job = AIJob(
            id=uuid.uuid4(),
            budget_id=budget.id,
            kind="receipt",
            status="done",
            attempts=1,
            payload={"account_id": str(account.id)},
            result={"draft": {"payee": "Hardware Store", "card_last4": last4}},
        )
        db_session.add(job)
        await db_session.commit()
        return job

    async def _served(self, api_client, budget, job):
        r = await api_client.get(f"/api/v1/{budget.id}/ai/jobs/{job.id}")
        assert r.status_code == 200, r.text
        return r.json()["card_ending_account_id"]

    async def test_the_account_whose_card_paid_as_of_now(self, db_session, api_client):
        budget, sapphire, harborstone = await _setup(db_session, api_client)
        job = await self._job(db_session, budget, harborstone, "4417")
        # Not on file yet: nobody's card.
        assert await self._served(api_client, budget, job) is None
        # Remembered after the scan: the answer follows the table, not the scan.
        await _add(api_client, budget, sapphire, "4417")
        assert await self._served(api_client, budget, job) == str(sapphire.id)

    async def test_a_receipt_without_a_card_names_nobody(self, db_session, api_client):
        budget, sapphire, _ = await _setup(db_session, api_client)
        await _add(api_client, budget, sapphire, "4417")
        job = await self._job(db_session, budget, sapphire, None)
        assert await self._served(api_client, budget, job) is None

    async def test_the_list_carries_it_too(self, db_session, api_client):
        budget, sapphire, _ = await _setup(db_session, api_client)
        await _add(api_client, budget, sapphire, "4417")
        await self._job(db_session, budget, sapphire, "4417")
        r = await api_client.get(f"/api/v1/{budget.id}/ai/jobs")
        assert r.status_code == 200, r.text
        assert [j["card_ending_account_id"] for j in r.json()["jobs"]] == [str(sapphire.id)]
