"""Rules the wishlist stated on the client, or stated twice, or not at all.

Each of these was reachable through the API exactly as written: the browser
filtered a picker the server did not, a wish outlived its envelope and could
never be given another, a reorder naming half the list renumbered it into
collisions, and ⌘Z restored a wish's link without re-deriving the tag that
is supposed to be derived from it.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from igab.guide import wishlist_service

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
)

TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)


class _FrozenDate(date):
    @classmethod
    def today(cls) -> date:
        return TODAY


@pytest.fixture(autouse=True)
def _one_today(monkeypatch):
    monkeypatch.setattr(wishlist_service, "date", _FrozenDate)


async def _budget(db_session, api_client):
    return await create_budget(db_session, api_client.test_user)


def _url(budget) -> str:
    return f"/api/v1/{budget.id}/wishlist"


async def _add(api_client, budget, **body):
    body.setdefault("name", "Bike")
    body.setdefault("cost", "1800")
    body.setdefault("client_today", TODAY.isoformat())
    r = await api_client.post(_url(budget), json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _plain_category(db_session, budget, name):
    group = await create_category_group(db_session, budget, "Everyday")
    return await create_category(db_session, budget, group, name)


async def _items(api_client, budget):
    return (await api_client.get(_url(budget))).json()["items"]


async def _tags_on(api_client, budget, category_id) -> list[str]:
    r = await api_client.get(f"/api/v1/{budget.id}/categories", params={"include_archived": "true"})
    for row in r.json():
        if row["id"] == category_id:
            return [t["name"].lower() for t in row.get("tags", [])]
    raise AssertionError(f"category {category_id} is not in the budget")


class TestWhatMayFundAWish:
    """`is_assignable` is the server's rule now. The client filtered its
    pickers on it; nothing stopped an API or MCP caller funding a wish from
    an income category or a card's set-aside, and reach then read a card's
    money as savings towards a bicycle."""

    async def test_an_income_category_cannot_fund_a_wish(self, db_session, api_client):
        """Money assigned to a system-group category would neither reduce
        Ready to Assign nor ever come back out — so a wish "funded" from one
        would read as saving towards itself."""
        budget = await _budget(db_session, api_client)
        income_group = await create_category_group(db_session, budget, "Income", is_system=True)
        paycheque = await create_category(db_session, budget, income_group, "Paycheque")

        r = await api_client.post(
            _url(budget),
            json={
                "name": "Bike",
                "cost": "100",
                "client_today": TODAY.isoformat(),
                "funding": {"mode": "existing", "category_id": str(paycheque.id)},
            },
        )
        assert r.status_code == 409, r.text
        assert "cannot fund a wish" in r.json()["detail"]

    async def test_a_project_is_held_to_the_same_rule(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        income_group = await create_category_group(db_session, budget, "Income", is_system=True)
        paycheque = await create_category(db_session, budget, income_group, "Paycheque")

        r = await api_client.post(
            f"{_url(budget)}/projects",
            json={"name": "Japan trip", "category_id": str(paycheque.id)},
        )
        assert r.status_code == 409, r.text

    async def test_an_archived_envelope_cannot_fund_a_wish(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        old = await _plain_category(db_session, budget, "Old Fund")
        r = await api_client.post(
            f"/api/v1/{budget.id}/categories/archive",
            json={"category_ids": [str(old.id)], "month": THIS_MONTH.isoformat()},
        )
        assert r.status_code in (200, 204), r.text

        r = await api_client.post(
            _url(budget),
            json={
                "name": "Bike",
                "cost": "100",
                "client_today": TODAY.isoformat(),
                "funding": {"mode": "existing", "category_id": str(old.id)},
            },
        )
        assert r.status_code == 409, r.text

    async def test_an_ordinary_envelope_still_funds_one(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        holiday = await _plain_category(db_session, budget, "Holiday")
        wish = await _add(
            api_client, budget, funding={"mode": "existing", "category_id": str(holiday.id)}
        )
        assert wish["funding"]["category_name"] == "Holiday"


class TestAWishThatOutlivedItsEnvelope:
    async def _orphaned(self, db_session, api_client, budget):
        """A wish whose own envelope was deleted underneath it."""
        wish = await _add(api_client, budget, funding={"mode": "own"})
        cat_id = wish["funding"]["category_id"]
        r = await api_client.delete(
            f"/api/v1/categories/{cat_id}", params={"month": THIS_MONTH.isoformat()}
        )
        assert r.status_code in (200, 204), r.text
        return wish, cat_id

    async def test_it_reads_as_unlinked(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish, _ = await self._orphaned(db_session, api_client, budget)
        [row] = await _items(api_client, budget)
        assert row["funding"]["mode"] == "none"

    async def test_own_funding_gives_it_a_new_envelope(self, db_session, api_client):
        """The no-op that could not be got past: `own` saw a stale link, took
        it for an envelope and returned, so the form offered to make one and
        nothing happened — forever."""
        budget = await _budget(db_session, api_client)
        wish, gone = await self._orphaned(db_session, api_client, budget)

        r = await api_client.patch(
            f"{_url(budget)}/{wish['id']}", json={"funding": {"mode": "own"}}
        )
        assert r.status_code == 200, r.text
        assert r.json()["funding"]["mode"] == "own"
        assert r.json()["funding"]["category_id"] != gone

    async def test_a_cost_edit_does_not_write_a_goal_onto_the_dead_row(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        wish, gone = await self._orphaned(db_session, api_client, budget)

        r = await api_client.patch(f"{_url(budget)}/{wish['id']}", json={"cost": "2500"})
        assert r.status_code == 200, r.text

        target = await api_client.get(f"/api/v1/categories/{gone}/target")
        assert target.status_code == 404 or target.json() is None


class TestReorderNamesTheWholeList:
    async def test_a_subset_is_refused_rather_than_silently_colliding(self, db_session, api_client):
        """It used to accept it: the wishes left out kept their old numbers
        and collided with the renumbered ones, so two wishes claimed one slot
        and the queue order became whatever the sort fell back on."""
        budget = await _budget(db_session, api_client)
        a = await _add(api_client, budget, name="A")
        b = await _add(api_client, budget, name="B")
        await _add(api_client, budget, name="C")

        r = await api_client.post(f"{_url(budget)}/reorder", json={"item_ids": [b["id"], a["id"]]})
        assert r.status_code == 409, r.text

    async def test_naming_them_all_reorders(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        a = await _add(api_client, budget, name="A")
        b = await _add(api_client, budget, name="B")
        c = await _add(api_client, budget, name="C")

        r = await api_client.post(
            f"{_url(budget)}/reorder", json={"item_ids": [c["id"], a["id"], b["id"]]}
        )
        assert r.status_code == 204, r.text
        assert [w["name"] for w in await _items(api_client, budget)] == ["C", "A", "B"]

    async def test_an_ended_wish_need_not_be_named(self, db_session, api_client):
        """The list the user drags shows open wishes only, so history keeps
        its slot rather than having to be listed."""
        budget = await _budget(db_session, api_client)
        a = await _add(api_client, budget, name="A")
        b = await _add(api_client, budget, name="B")
        old = await _add(api_client, budget, name="Old")
        r = await api_client.patch(
            f"{_url(budget)}/{old['id']}",
            json={"status": "dropped", "client_today": TODAY.isoformat()},
        )
        assert r.status_code == 200, r.text

        r = await api_client.post(f"{_url(budget)}/reorder", json={"item_ids": [b["id"], a["id"]]})
        assert r.status_code == 204, r.text
        assert [w["name"] for w in await _items(api_client, budget)] == ["B", "A"]


class TestTheDerivedTagSurvivesUndo:
    """`wishlist` is on an envelope iff an open wish draws on it. Undo writes
    a snapshot straight onto the row, so the rule has to be re-run — or the
    tag freezes at whatever the mutation made it."""

    async def test_undoing_a_drop_tags_the_envelope_again(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        holiday = await _plain_category(db_session, budget, "Holiday")
        wish = await _add(
            api_client, budget, funding={"mode": "existing", "category_id": str(holiday.id)}
        )
        assert "wishlist" in await _tags_on(api_client, budget, str(holiday.id))

        r = await api_client.patch(
            f"{_url(budget)}/{wish['id']}",
            json={"status": "dropped", "client_today": TODAY.isoformat()},
        )
        assert r.status_code == 200, r.text
        assert "wishlist" not in await _tags_on(api_client, budget, str(holiday.id))

        r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert r.status_code == 200, r.text

        # The wish is open again, so the envelope is a wishlist envelope again.
        assert "wishlist" in await _tags_on(api_client, budget, str(holiday.id))

    async def test_undoing_a_wish_delete_tags_the_envelope_again(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        holiday = await _plain_category(db_session, budget, "Holiday")
        wish = await _add(
            api_client, budget, funding={"mode": "existing", "category_id": str(holiday.id)}
        )

        r = await api_client.delete(f"{_url(budget)}/{wish['id']}")
        assert r.status_code == 200, r.text
        assert "wishlist" not in await _tags_on(api_client, budget, str(holiday.id))

        r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert r.status_code == 200, r.text
        assert "wishlist" in await _tags_on(api_client, budget, str(holiday.id))


class TestEndingsAreStampedWithThePersonsDay:
    async def test_a_drop_takes_the_browsers_date(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget)
        # A day the server's clock cannot be on, in either direction.
        theirs = TODAY - timedelta(days=2)

        r = await api_client.patch(
            f"{_url(budget)}/{wish['id']}",
            json={"status": "dropped", "client_today": theirs.isoformat()},
        )
        assert r.status_code == 200, r.text
        assert r.json()["dropped_at"] == theirs.isoformat()

    async def test_restating_a_status_does_not_move_the_stamp(self, db_session, api_client):
        """Re-sending `done` rewrote when the wish ended, every time anything
        else about it was saved."""
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget)
        first = TODAY - timedelta(days=5)
        r = await api_client.patch(
            f"{_url(budget)}/{wish['id']}",
            json={"status": "done", "client_today": first.isoformat()},
        )
        assert r.json()["done_at"] == first.isoformat()

        r = await api_client.patch(
            f"{_url(budget)}/{wish['id']}",
            json={"status": "done", "notes": "still done", "client_today": TODAY.isoformat()},
        )
        assert r.status_code == 200, r.text
        assert r.json()["done_at"] == first.isoformat()

    async def test_reopening_clears_both_stamps(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget)
        await api_client.patch(
            f"{_url(budget)}/{wish['id']}",
            json={"status": "dropped", "client_today": TODAY.isoformat()},
        )
        r = await api_client.patch(
            f"{_url(budget)}/{wish['id']}",
            json={"status": "open", "client_today": TODAY.isoformat()},
        )
        assert r.status_code == 200, r.text
        assert r.json()["dropped_at"] is None
        assert r.json()["done_at"] is None

    async def test_an_affirmation_is_dated_by_the_person_too(self, db_session, api_client):
        """The review cadence measures from the affirmation to today, and
        `added_on` is already a local date — comparing a UTC day with local
        ones put the next review a day out."""
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget)
        theirs = TODAY - timedelta(days=1)

        r = await api_client.post(
            f"{_url(budget)}/{wish['id']}/affirm", params={"today": theirs.isoformat()}
        )
        assert r.status_code == 204, r.text

        # Due again exactly `review_after_days` after the day they answered,
        # measured in their dates end to end.
        settings = (await api_client.get(_url(budget))).json()["settings"]
        due_day = theirs + timedelta(days=settings["review_after_days"])
        before = (
            await api_client.get(
                _url(budget), params={"today": (due_day - timedelta(days=1)).isoformat()}
            )
        ).json()
        assert before["items"][0]["review_due"] is False
        after = (await api_client.get(_url(budget), params={"today": due_day.isoformat()})).json()
        assert after["items"][0]["review_due"] is True

    async def test_the_list_answers_for_the_day_the_browser_names(self, db_session, api_client):
        """Cooling-off is a question about a particular day. Asked without
        one the server answered for its own, which is already tomorrow every
        evening west of UTC."""
        budget = await _budget(db_session, api_client)
        await _add(api_client, budget, cooling_days=1)

        today = (await api_client.get(_url(budget), params={"today": TODAY.isoformat()})).json()
        assert today["items"][0]["cooling"] is True

        later = TODAY + timedelta(days=3)
        after = (await api_client.get(_url(budget), params={"today": later.isoformat()})).json()
        assert after["items"][0]["cooling"] is False


class TestAFreeWishIsAlwaysReachable:
    async def test_even_on_an_overspent_envelope(self, db_session, api_client):
        """`available >= cumulative` alone called a free wish eight months
        away on an overspent envelope, while its progress bar read full."""
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget, account_type="checking")
        await create_transaction(db_session, budget, account, "1000.00", TODAY)
        holiday = await _plain_category(db_session, budget, "Holiday")
        await create_transaction(db_session, budget, account, "-60.00", TODAY, category=holiday)

        wish = await _add(
            api_client,
            budget,
            cost="0",
            funding={"mode": "existing", "category_id": str(holiday.id)},
        )
        [row] = await _items(api_client, budget)
        assert row["id"] == wish["id"]
        assert row["reach"]["state"] == "now"
        assert Decimal(str(row["reach"]["progress"])) == Decimal("1")
