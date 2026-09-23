"""Ending a wish is not the end of its envelope.

Dropping a wish used to be a status flip. The envelope stayed on the budget
page holding money, still carrying a savings goal for something nobody was
going to buy, and no screen said so — the money was simply parked under a
name the person had already decided against.

`settlement` is the served fact that says the books are still open, and
`POST .../settle` is the step that closes them: the money goes where the
person chose, the goal goes with the wish, and the envelope is archived
unless they want to keep it. One change batch, so ⌘Z puts all three back.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from igab.db.models import Category
from igab.guide import wishlist_service

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    money,
)

TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)


class _FrozenDate(date):
    @classmethod
    def today(cls) -> date:
        return TODAY


@pytest.fixture(autouse=True)
def _one_today(monkeypatch):
    """One clock for the module and the service — see test_wishlist_api."""
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


async def _assign(api_client, budget, category_id, amount):
    r = await api_client.patch(
        f"/api/v1/categories/{category_id}/assignment",
        params={"budget_id": str(budget.id), "month": THIS_MONTH.isoformat()},
        json={"amount": amount},
    )
    assert r.status_code in (200, 204), r.text


async def _income(db_session, budget, amount="5000.00"):
    account = await create_account(db_session, budget, account_type="checking")
    await create_transaction(db_session, budget, account, amount, TODAY)
    return account


async def _end(api_client, budget, wish_id, status="dropped"):
    r = await api_client.patch(f"{_url(budget)}/{wish_id}", json={"status": status})
    assert r.status_code == 200, r.text
    return r.json()


async def _wish(api_client, budget, wish_id):
    body = (await api_client.get(_url(budget))).json()
    for row in body["items"] + body["history"]:
        if row["id"] == wish_id:
            return row
    raise AssertionError(f"wish {wish_id} is on neither list")


async def _settle(api_client, budget, wish_id, **body):
    return await api_client.post(f"{_url(budget)}/{wish_id}/settle", json=body)


async def _tba(api_client, budget) -> Decimal:
    r = await api_client.get(f"/api/v1/{budget.id}/months/{THIS_MONTH.isoformat()}")
    return Decimal(r.json()["to_be_assigned"])


async def _is_archived(api_client, budget, category_id) -> bool:
    r = await api_client.get(f"/api/v1/{budget.id}/categories", params={"include_archived": "true"})
    for row in r.json():
        if row["id"] == category_id:
            return bool(row["is_archived"])
    raise AssertionError(f"category {category_id} is not in the budget")


async def _available(api_client, budget, category_id) -> Decimal:
    r = await api_client.get(f"/api/v1/{budget.id}/months/{THIS_MONTH.isoformat()}")
    for row in r.json()["category_balances"]:
        if row["category_id"] == category_id:
            return money(row["available"])
    raise AssertionError(f"category {category_id} is not on the month")


async def _plain_category(db_session, budget, name):
    """An ordinary envelope outside the Wishlist group."""
    group = await create_category_group(db_session, budget, "Everyday")
    return await create_category(db_session, budget, group, name)


async def _funded_wish(db_session, api_client, budget, amount="400.00", **body):
    """A wish with an envelope of its own, holding `amount`."""
    await _income(db_session, budget)
    wish = await _add(api_client, budget, funding={"mode": "own"}, **body)
    await _assign(api_client, budget, wish["funding"]["category_id"], amount)
    return wish


class TestTheServedFact:
    async def test_an_open_wish_is_never_unfinished_business(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _funded_wish(db_session, api_client, budget)
        assert (await _wish(api_client, budget, wish["id"]))["settlement"] is None

    @pytest.mark.parametrize("status", ["dropped", "done"])
    async def test_ending_a_funded_wish_leaves_its_envelope_standing(
        self, db_session, api_client, status
    ):
        """Both endings, not just the one that reads like a mistake. A wish
        you bought leaves behind a goal that is now meaningless and, more
        often than not, a remainder."""
        budget = await _budget(db_session, api_client)
        wish = await _funded_wish(db_session, api_client, budget)

        await _end(api_client, budget, wish["id"], status)

        settlement = (await _wish(api_client, budget, wish["id"]))["settlement"]
        assert settlement is not None
        assert settlement["name"] == "Bike"
        assert money(settlement["available"]) == Decimal("400.00")
        assert settlement["has_goal"] is True

    async def test_an_empty_envelope_still_asks_while_it_carries_the_goal(
        self, db_session, api_client
    ):
        """Nothing to move, but the goal is still the wish's cost — the
        budget page would go on asking for $1,800 towards a dropped wish."""
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget, funding={"mode": "own"})

        await _end(api_client, budget, wish["id"])

        settlement = (await _wish(api_client, budget, wish["id"]))["settlement"]
        assert settlement is not None
        assert money(settlement["available"]) == Decimal("0.00")
        assert settlement["has_goal"] is True

    async def test_a_wish_funded_from_a_shared_envelope_asks_nothing(self, db_session, api_client):
        """It never owned the envelope, so there is nothing of its own to
        settle — the rent category is not the wish's to archive."""
        budget = await _budget(db_session, api_client)
        rent = await _plain_category(db_session, budget, "Rent")
        wish = await _add(
            api_client, budget, funding={"mode": "existing", "category_id": str(rent.id)}
        )

        await _end(api_client, budget, wish["id"])

        assert (await _wish(api_client, budget, wish["id"]))["settlement"] is None

    async def test_an_unfunded_wish_asks_nothing(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget)
        await _end(api_client, budget, wish["id"])
        assert (await _wish(api_client, budget, wish["id"]))["settlement"] is None


class TestSettling:
    async def test_the_money_goes_to_ready_to_assign_by_default(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _funded_wish(db_session, api_client, budget)
        await _end(api_client, budget, wish["id"])
        before = await _tba(api_client, budget)

        r = await _settle(api_client, budget, wish["id"])
        assert r.status_code == 200, r.text

        assert await _tba(api_client, budget) == before + Decimal("400.00")

    async def test_the_money_can_go_to_a_chosen_envelope_instead(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        holiday = await _plain_category(db_session, budget, "Holiday")
        wish = await _funded_wish(db_session, api_client, budget)
        await _end(api_client, budget, wish["id"])
        before = await _tba(api_client, budget)

        r = await _settle(api_client, budget, wish["id"], destination_category_id=str(holiday.id))
        assert r.status_code == 200, r.text

        assert await _available(api_client, budget, str(holiday.id)) == Decimal("400.00")
        # Straight across: the money never passed through Ready to Assign.
        assert await _tba(api_client, budget) == before

    async def test_it_drops_the_goal_and_archives_the_envelope(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _funded_wish(db_session, api_client, budget)
        cat_id = wish["funding"]["category_id"]
        await _end(api_client, budget, wish["id"])

        assert (await _settle(api_client, budget, wish["id"])).status_code == 200

        target = await api_client.get(f"/api/v1/categories/{cat_id}/target")
        assert target.status_code == 404 or target.json() is None
        assert await _is_archived(api_client, budget, cat_id) is True

    async def test_settling_clears_the_prompt(self, db_session, api_client):
        """Derived, not stamped: what settle removes is exactly what the
        served fact reads, so the two cannot disagree."""
        budget = await _budget(db_session, api_client)
        wish = await _funded_wish(db_session, api_client, budget)
        await _end(api_client, budget, wish["id"])

        settled = (await _settle(api_client, budget, wish["id"])).json()

        assert settled["settlement"] is None
        assert (await _wish(api_client, budget, wish["id"]))["settlement"] is None

    async def test_keeping_the_envelope_empties_it_and_leaves_it_on_the_page(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        wish = await _funded_wish(db_session, api_client, budget)
        cat_id = wish["funding"]["category_id"]
        await _end(api_client, budget, wish["id"])

        r = await _settle(api_client, budget, wish["id"], keep_envelope=True)
        assert r.status_code == 200, r.text

        assert await _is_archived(api_client, budget, cat_id) is False
        assert await _available(api_client, budget, cat_id) == Decimal("0.00")
        # The goal went with the wish — what is left is a plain envelope to
        # re-purpose, not one still asking for a dropped wish's cost.
        assert r.json()["settlement"] is None

    async def test_an_overspent_envelope_is_covered_by_the_destination(
        self, db_session, api_client
    ):
        """The sign that would have been missed: an envelope left standing at
        -60 is a hole someone has to cover, and archiving it as-is loses
        track of real money. The move runs the other way."""
        budget = await _budget(db_session, api_client)
        account = await _income(db_session, budget)
        wish = await _add(api_client, budget, funding={"mode": "own"})
        cat_id = wish["funding"]["category_id"]
        await _assign(api_client, budget, cat_id, "40.00")
        envelope = await db_session.get(Category, uuid.UUID(cat_id))
        await create_transaction(db_session, budget, account, "-100.00", TODAY, category=envelope)
        await _end(api_client, budget, wish["id"])

        settlement = (await _wish(api_client, budget, wish["id"]))["settlement"]
        assert money(settlement["available"]) == Decimal("-60.00")

        before = await _tba(api_client, budget)
        r = await _settle(api_client, budget, wish["id"])
        assert r.status_code == 200, r.text

        assert await _tba(api_client, budget) == before - Decimal("60.00")
        assert r.json()["settlement"] is None

    async def test_the_leftover_envelope_can_be_deleted_once_the_wish_has_ended(
        self, db_session, api_client
    ):
        """An ended wish keeps its link as history. Counting those as live
        references made the envelope unclearable forever — the very state
        settling exists to end."""
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget, funding={"mode": "own"})
        cat_id = wish["funding"]["category_id"]

        blocked = await api_client.get(
            f"/api/v1/categories/{cat_id}/delete-preview",
            params={"month": THIS_MONTH.isoformat()},
        )
        assert blocked.status_code == 200, blocked.text
        assert any(r["kind"] == "wish" for r in blocked.json()["references"])

        await _end(api_client, budget, wish["id"])

        after = await api_client.get(
            f"/api/v1/categories/{cat_id}/delete-preview",
            params={"month": THIS_MONTH.isoformat()},
        )
        assert not any(r["kind"] == "wish" for r in after.json()["references"])


class TestSettlingRefuses:
    async def test_an_open_wish_has_nothing_to_settle(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _funded_wish(db_session, api_client, budget)

        r = await _settle(api_client, budget, wish["id"])
        assert r.status_code == 409
        assert "done or dropped" in r.json()["detail"]

    async def test_a_wish_without_its_own_envelope_has_nothing_to_settle(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget)
        await _end(api_client, budget, wish["id"])

        r = await _settle(api_client, budget, wish["id"])
        assert r.status_code == 409
        assert "no envelope of its own" in r.json()["detail"]

    async def test_it_refuses_to_move_the_money_into_the_envelope_being_settled(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        wish = await _funded_wish(db_session, api_client, budget)
        cat_id = wish["funding"]["category_id"]
        await _end(api_client, budget, wish["id"])

        r = await _settle(api_client, budget, wish["id"], destination_category_id=cat_id)
        assert r.status_code == 409

    async def test_settling_twice_refuses_rather_than_archiving_again(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _funded_wish(db_session, api_client, budget)
        await _end(api_client, budget, wish["id"])
        assert (await _settle(api_client, budget, wish["id"])).status_code == 200

        r = await _settle(api_client, budget, wish["id"])
        assert r.status_code == 409
        assert "already archived" in r.json()["detail"]


class TestSettleUndo:
    async def test_one_cmdz_puts_back_the_money_the_goal_and_the_envelope(
        self, db_session, api_client
    ):
        """The reason settle is one batch. Undoing it a keystroke at a time
        would let the money and the envelope it came from part company."""
        budget = await _budget(db_session, api_client)
        wish = await _funded_wish(db_session, api_client, budget)
        cat_id = wish["funding"]["category_id"]
        await _end(api_client, budget, wish["id"])
        before = await _tba(api_client, budget)

        assert (await _settle(api_client, budget, wish["id"])).status_code == 200
        assert await _tba(api_client, budget) == before + Decimal("400.00")

        r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert r.status_code == 200, r.text

        assert await _tba(api_client, budget) == before
        assert await _available(api_client, budget, cat_id) == Decimal("400.00")
        assert await _is_archived(api_client, budget, cat_id) is False
        target = await api_client.get(f"/api/v1/categories/{cat_id}/target")
        assert target.status_code == 200 and target.json() is not None
        # And the prompt is back, because the facts it reads are back.
        assert (await _wish(api_client, budget, wish["id"]))["settlement"] is not None
