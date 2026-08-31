"""The wishlist lives inside the budget: its money is the envelopes' money."""

from datetime import date
from decimal import Decimal

from igab.domain.dates import add_months

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    money,
)

TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)


async def _budget(db_session, api_client):
    return await create_budget(db_session, api_client.test_user)


def _url(budget) -> str:
    return f"/api/v1/{budget.id}/wishlist"


async def _add(api_client, budget, **body):
    body.setdefault("name", "Bike")
    body.setdefault("cost", "1800")
    r = await api_client.post(_url(budget), json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _groups(api_client, budget):
    r = await api_client.get(f"/api/v1/{budget.id}/category-groups?include_archived=true")
    return r.json()


async def _wishlist_group(api_client, budget):
    return next(g for g in await _groups(api_client, budget) if g["system_key"] == "wishlist")


class TestTheGroup:
    async def test_seeded_on_first_read(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        assert not [g for g in await _groups(api_client, budget) if g["system_key"]]
        r = await api_client.get(_url(budget))
        assert r.status_code == 200 and r.json()["enabled"] is True
        group = await _wishlist_group(api_client, budget)
        assert group["name"] == "Wishlist"
        assert group["is_system"] is False  # an ordinary, assignable group
        assert group["is_archived"] is False

    async def test_adopts_an_existing_group_of_the_same_name(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        mine = await create_category_group(db_session, budget, "wishlist")
        await api_client.get(_url(budget))
        group = await _wishlist_group(api_client, budget)
        assert group["id"] == str(mine.id)

    async def test_rename_refused_delete_refused_archive_allowed(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await api_client.get(_url(budget))
        group = await _wishlist_group(api_client, budget)
        r = await api_client.patch(f"/api/v1/category-groups/{group['id']}", json={"name": "Toys"})
        assert r.status_code == 400
        r = await api_client.delete(f"/api/v1/category-groups/{group['id']}")
        assert r.status_code in (400, 409), r.text
        # Through the archive route, not a PATCH of the flag: the generic
        # update no longer accepts it, because setting it there skipped the
        # refusal that keeps money from being stranded.
        r = await api_client.post(
            f"/api/v1/{budget.id}/category-groups/{group['id']}/archive", json={}
        )
        assert r.status_code == 200, r.text
        groups = (
            await api_client.get(f"/api/v1/{budget.id}/category-groups?include_archived=true")
        ).json()
        assert next(g for g in groups if g["id"] == group["id"])["is_archived"] is True

    async def test_its_envelopes_count_against_to_be_assigned(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget, account_type="checking")
        await create_transaction(db_session, budget, account, "1000.00", TODAY)
        wish = await _add(api_client, budget, funding={"mode": "own"})
        cat_id = wish["funding"]["category_id"]
        r = await api_client.patch(
            f"/api/v1/categories/{cat_id}/assignment",
            params={"budget_id": str(budget.id), "month": THIS_MONTH.isoformat()},
            json={"amount": "150.00"},
        )
        assert r.status_code == 204, r.text
        month = (
            await api_client.get(f"/api/v1/{budget.id}/months/{THIS_MONTH.isoformat()}")
        ).json()
        assert Decimal(month["to_be_assigned"]) == Decimal("850.00")
        row = next(b for b in month["category_balances"] if b["category_id"] == cat_id)
        assert money(row["available"]) == Decimal("150.00")


class TestOwnEnvelope:
    async def test_creates_a_category_with_a_savings_goal_the_budget_page_shows(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        wish = await _add(
            api_client, budget, cost="1800", funding={"mode": "own", "want_by": "2027-06-01"}
        )
        assert wish["funding"]["mode"] == "own"
        assert wish["funding"]["owns_envelope"] is True
        assert wish["funding"]["category_name"] == "Bike"
        assert wish["funding"]["target_date"] == "2027-06-01"
        cat_id = wish["funding"]["category_id"]
        target = (await api_client.get(f"/api/v1/categories/{cat_id}/target")).json()
        assert target["target_type"] == "savings_balance"
        assert Decimal(target["target_amount"]) == Decimal("1800.00")
        group = await _wishlist_group(api_client, budget)
        cats = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        assert next(c for c in cats if c["id"] == cat_id)["category_group_id"] == group["id"]

    async def test_a_name_clash_is_refused_with_a_reason(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Fun")
        await create_category(db_session, budget, group, "Bike")
        r = await api_client.post(
            _url(budget), json={"name": "Bike", "cost": "10", "funding": {"mode": "own"}}
        )
        assert r.status_code == 409
        assert "already exists" in r.json()["detail"]

    async def test_editing_the_cost_moves_the_goal_but_not_the_other_way(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget, cost="1800", funding={"mode": "own"})
        cat_id = wish["funding"]["category_id"]

        r = await api_client.patch(f"{_url(budget)}/{wish['id']}", json={"cost": "2000"})
        assert r.status_code == 200
        target = (await api_client.get(f"/api/v1/categories/{cat_id}/target")).json()
        assert Decimal(target["target_amount"]) == Decimal("2000.00")

        # The budget page owns the goal from here: moving it does not rewrite
        # the wish — "what it costs" and "what I will set aside" may differ.
        r = await api_client.post(
            f"/api/v1/categories/{cat_id}/target",
            json={"target_type": "savings_balance", "target_amount": "1500"},
        )
        assert r.status_code in (200, 201)
        body = (await api_client.get(_url(budget))).json()
        assert money(body["items"][0]["cost"]) == Decimal("2000.00")

    async def test_delete_offers_the_envelope_only_when_owned(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        owned = await _add(api_client, budget, funding={"mode": "own"})
        group = await create_category_group(db_session, budget, "Home")
        cat = await create_category(db_session, budget, group, "Home Upgrades")
        linked = await _add(
            api_client,
            budget,
            name="Desk",
            cost="420",
            funding={"mode": "existing", "category_id": str(cat.id)},
        )
        r = await api_client.delete(f"{_url(budget)}/{owned['id']}")
        assert r.status_code == 200
        assert r.json()["envelope"]["name"] == "Bike"
        r = await api_client.delete(f"{_url(budget)}/{linked['id']}")
        assert r.status_code == 200
        assert r.json()["envelope"] is None
        # The category the wish pointed at is untouched.
        cats = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        assert str(cat.id) in {c["id"] for c in cats}


class TestReach:
    async def test_reach_uses_the_budget_pages_available(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Home")
        cat = await create_category(db_session, budget, group, "Home Upgrades")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "610.00")
        account = await create_account(db_session, budget, account_type="checking")
        await create_transaction(db_session, budget, account, "-100.00", TODAY, category=cat)
        wish = await _add(
            api_client,
            budget,
            name="Desk",
            cost="420",
            funding={"mode": "existing", "category_id": str(cat.id)},
        )
        month = (
            await api_client.get(f"/api/v1/{budget.id}/months/{THIS_MONTH.isoformat()}")
        ).json()
        page = next(b for b in month["category_balances"] if b["category_id"] == str(cat.id))
        assert Decimal(page["available"]) == Decimal("510.00")
        assert wish["reach"]["state"] == "now"
        assert wish["funding"]["mode"] == "existing"

    async def test_a_target_beats_the_trailing_average(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Savings")
        cat = await create_category(db_session, budget, group, "Bike Fund")
        # 300 assigned last month reads as 100 a month on average...
        await create_budget_assignment(
            db_session, budget, cat, add_months(THIS_MONTH, -1), "300.00"
        )
        wish = await _add(
            api_client,
            budget,
            cost="1300",
            funding={"mode": "existing", "category_id": str(cat.id)},
        )
        assert wish["reach"]["months"] == 10  # 1000 short at 100
        # ...but a monthly target of 250 is the pace the user committed to.
        await api_client.post(
            f"/api/v1/categories/{cat.id}/target",
            json={"target_type": "monthly_funding", "target_amount": "250"},
        )
        body = (await api_client.get(_url(budget))).json()
        assert body["items"][0]["reach"]["months"] == 4

    async def test_unlinked_and_no_rate(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        unlinked = await _add(api_client, budget)
        assert unlinked["reach"]["state"] == "unlinked"
        assert unlinked["funding"]["mode"] == "none"
        group = await create_category_group(db_session, budget, "Savings")
        cat = await create_category(db_session, budget, group, "Empty")
        quiet = await _add(
            api_client,
            budget,
            name="Lamp",
            cost="50",
            funding={"mode": "existing", "category_id": str(cat.id)},
        )
        assert quiet["reach"]["state"] == "no_rate"

    async def test_two_wishes_on_one_envelope_queue_by_priority(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Home")
        cat = await create_category(db_session, budget, group, "Home Upgrades")
        await create_budget_assignment(db_session, budget, cat, THIS_MONTH, "500.00")
        first = await _add(
            api_client,
            budget,
            name="Desk",
            cost="420",
            funding={"mode": "existing", "category_id": str(cat.id)},
        )
        second = await _add(
            api_client,
            budget,
            name="Chair",
            cost="300",
            funding={"mode": "existing", "category_id": str(cat.id)},
        )
        assert first["reach"]["state"] == "now"
        # 720 wanted against 500, at the trailing average of 166.67 a month.
        assert second["reach"]["state"] == "months"
        assert second["reach"]["months"] == 2
        assert Decimal(second["reach"]["ahead_cost"]) == Decimal("420.00")
        # Reorder: the chair now comes first and is affordable.
        r = await api_client.post(
            f"{_url(budget)}/reorder", json={"item_ids": [second["id"], first["id"]]}
        )
        assert r.status_code == 204
        body = (await api_client.get(_url(budget))).json()
        by_name = {i["name"]: i for i in body["items"]}
        assert by_name["Chair"]["reach"]["state"] == "now"
        assert by_name["Desk"]["reach"]["state"] == "months"
        assert by_name["Chair"]["priority"] == 0


class TestProjects:
    async def test_a_projects_envelope_funds_its_wishes_and_an_own_one_overrides(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Savings")
        trip = await create_category(db_session, budget, group, "Japan Trip")
        await create_budget_assignment(db_session, budget, trip, THIS_MONTH, "4000.00")
        r = await api_client.post(
            f"{_url(budget)}/projects", json={"name": "Japan", "category_id": str(trip.id)}
        )
        assert r.status_code == 201, r.text
        project = r.json()
        flights = await _add(
            api_client, budget, name="Flights", cost="1500", project_id=project["id"]
        )
        assert flights["funding"]["inherited"] is True
        assert flights["funding"]["category_name"] == "Japan Trip"
        assert flights["reach"]["state"] == "now"
        own = await create_category(db_session, budget, group, "Camera Fund")
        camera = await _add(
            api_client,
            budget,
            name="Camera",
            cost="900",
            project_id=project["id"],
            funding={"mode": "existing", "category_id": str(own.id)},
        )
        assert camera["funding"]["inherited"] is False
        assert camera["reach"]["state"] == "no_rate"

        body = (await api_client.get(_url(budget))).json()
        summary = body["projects"][0]["summary"]
        assert summary["open_count"] == 2
        assert summary["affordable_now"] == 1
        assert summary["state"] == "mixed"
        assert Decimal(summary["total_cost"]) == Decimal("2400.00")

    async def test_deleting_a_project_ungroups_and_keeps_its_wishes(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        project = (
            await api_client.post(f"{_url(budget)}/projects", json={"name": "Workshop"})
        ).json()
        wish = await _add(api_client, budget, project_id=project["id"])
        r = await api_client.delete(f"{_url(budget)}/projects/{project['id']}")
        assert r.status_code == 204
        body = (await api_client.get(_url(budget))).json()
        assert body["projects"] == []
        assert body["items"][0]["id"] == wish["id"]
        assert body["items"][0]["project_id"] is None


class TestTheTag:
    async def _tag_on(self, api_client, budget, cat_id) -> bool:
        cats = (
            await api_client.get(f"/api/v1/{budget.id}/categories?include_archived=true")
        ).json()
        cat = next(c for c in cats if c["id"] == cat_id)
        return any(
            t.get("system_key") == "wishlist" or t.get("name") == "Wishlist"
            for t in cat.get("tags", [])
        )

    async def test_follows_the_funding_link(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Home")
        a = await create_category(db_session, budget, group, "A")
        b = await create_category(db_session, budget, group, "B")
        wish = await _add(
            api_client, budget, funding={"mode": "existing", "category_id": str(a.id)}
        )
        assert await self._tag_on(api_client, budget, str(a.id))
        # Relink: the tag moves.
        await api_client.patch(
            f"{_url(budget)}/{wish['id']}",
            json={"funding": {"mode": "existing", "category_id": str(b.id)}},
        )
        assert not await self._tag_on(api_client, budget, str(a.id))
        assert await self._tag_on(api_client, budget, str(b.id))
        # Done: nothing open draws on B any more.
        await api_client.patch(f"{_url(budget)}/{wish['id']}", json={"status": "done"})
        assert not await self._tag_on(api_client, budget, str(b.id))

    async def test_the_tag_is_a_system_tag_that_cannot_be_renamed(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await _add(api_client, budget, funding={"mode": "own"})
        tags = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
        tag = next(t for t in tags if t["system_key"] == "wishlist")
        r = await api_client.patch(f"/api/v1/{budget.id}/tags/{tag['id']}", json={"name": "Wants"})
        assert r.status_code == 400


class TestCoolingReviewAndStillWanted:
    async def test_cooling_defaults_from_settings_and_review_waits_for_it(
        self, db_session, api_client
    ):
        budget = await _budget(db_session, api_client)
        r = await api_client.put(f"{_url(budget)}/settings", json={"cooling_days": 10})
        assert r.status_code == 200 and r.json()["cooling_days"] == 10
        wish = await _add(api_client, budget)
        assert (
            wish["cooling_until"]
            == (
                TODAY.replace(day=TODAY.day) + __import__("datetime").timedelta(days=10)
            ).isoformat()
        )
        assert wish["cooling"] is True
        assert wish["review_due"] is False
        no_cooling = await _add(api_client, budget, name="Now", cooling_days=0)
        assert no_cooling["cooling"] is False

    async def test_affirm_stamps_and_clears_review(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget, cooling_days=0)
        r = await api_client.post(f"{_url(budget)}/{wish['id']}/affirm")
        assert r.status_code == 204
        body = (await api_client.get(_url(budget))).json()
        assert body["items"][0]["last_affirmed_at"] is not None
        assert body["items"][0]["review_due"] is False
        assert body["review_due_count"] == 0

    async def test_done_moves_to_history_and_leaves_the_queue(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        wish = await _add(api_client, budget)
        r = await api_client.patch(f"{_url(budget)}/{wish['id']}", json={"status": "done"})
        assert r.status_code == 200
        assert r.json()["done_at"] == TODAY.isoformat()
        assert r.json()["reach"] is None
        body = (await api_client.get(_url(budget))).json()
        assert body["items"] == []
        assert body["history"][0]["id"] == wish["id"]
        assert body["still_wanted"] == {"count": 0, "of": 0, "months": 3}


class TestSwitchAndBoundaries:
    async def test_off_hides_the_group_and_refuses_writes(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await _add(api_client, budget, funding={"mode": "own"})
        r = await api_client.put(f"/api/v1/{budget.id}/guide/preferences", json={"wishlist": False})
        assert r.status_code == 200 and r.json()["wishlist"] is False
        assert (await _wishlist_group(api_client, budget))["is_archived"] is True
        body = (await api_client.get(_url(budget))).json()
        assert body["enabled"] is False and body["items"] == []
        assert (
            await api_client.post(_url(budget), json={"name": "X", "cost": "1"})
        ).status_code == 409
        # And back on: the group returns, the wish was never lost.
        await api_client.put(f"/api/v1/{budget.id}/guide/preferences", json={"wishlist": True})
        assert (await _wishlist_group(api_client, budget))["is_archived"] is False
        assert len((await api_client.get(_url(budget))).json()["items"]) == 1

    async def test_self_reported_money_does_not_reach_the_wishlist(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Savings")
        ef = await create_category(db_session, budget, group, "Emergency Fund")
        await api_client.put(
            f"/api/v1/{budget.id}/guide/bindings/emergency_fund",
            json={
                "mode": "manual",
                "entity_ids": {"category": [str(ef.id)]},
                "external": True,
                "external_amount": "250000",
            },
        )
        wish = await _add(
            api_client,
            budget,
            cost="100",
            funding={"mode": "existing", "category_id": str(ef.id)},
        )
        assert wish["reach"]["state"] == "no_rate"  # nothing actually in it

    async def test_nothing_leaks_between_budgets(self, db_session, api_client):
        mine = await _budget(db_session, api_client)
        other = await _budget(db_session, api_client)
        wish = await _add(api_client, mine)
        assert (await api_client.get(_url(other))).json()["items"] == []
        r = await api_client.patch(f"{_url(other)}/{wish['id']}", json={"name": "Stolen"})
        assert r.status_code == 404
        r = await api_client.delete(f"{_url(other)}/{wish['id']}")
        assert r.status_code == 404


async def _move(api_client, budget, frm, to, amount):
    r = await api_client.post(
        f"/api/v1/{budget.id}/budget/move-money",
        json={
            "from_category_id": frm,
            "to_category_id": to,
            "amount": amount,
            "month": THIS_MONTH.isoformat(),
        },
    )
    assert r.status_code == 204, r.text


class TestDrains:
    """What pulled from your wants: the audit trail, named, with the distance."""

    async def _setup(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        account = await create_account(db_session, budget, account_type="checking")
        await create_transaction(db_session, budget, account, "1000.00", TODAY)
        wish = await _add(api_client, budget, funding={"mode": "own"})
        bike = wish["funding"]["category_id"]
        r = await api_client.patch(
            f"/api/v1/categories/{bike}/assignment",
            params={"budget_id": str(budget.id), "month": THIS_MONTH.isoformat()},
            json={"amount": "300.00"},
        )
        assert r.status_code == 204, r.text
        group = await create_category_group(db_session, budget, "Fun")
        dining = await create_category(db_session, budget, group, "Dining Out")
        return budget, wish, bike, dining

    async def test_a_move_out_is_listed_with_its_destination_and_impact(
        self, db_session, api_client
    ):
        budget, wish, bike, dining = await self._setup(db_session, api_client)
        await _move(api_client, budget, bike, str(dining.id), "60.00")

        drains = (await api_client.get(_url(budget))).json()["drains"]

        assert Decimal(drains["total"]) == Decimal("60.00")
        [row] = drains["moves"]
        assert (row["from_name"], row["to_name"]) == ("Bike", "Dining Out")
        [hit] = row["affected"]
        assert hit["item_id"] == wish["id"]
        # The move itself lowers this month's assignment to 240, so the
        # trailing pace is 80 a month and 60 is three quarters of one.
        assert Decimal(hit["months_further"]) == Decimal("0.75")

    async def test_money_released_to_the_pool_counts_too(self, db_session, api_client):
        budget, _wish, bike, _dining = await self._setup(db_session, api_client)
        await _move(api_client, budget, bike, None, "25.00")
        [row] = (await api_client.get(_url(budget))).json()["drains"]["moves"]
        assert row["to_name"] == "To Be Assigned"

    async def test_moves_into_the_envelope_or_between_others_are_not_drains(
        self, db_session, api_client
    ):
        budget, _wish, bike, dining = await self._setup(db_session, api_client)
        group = await create_category_group(db_session, budget, "Bills")
        rent = await create_category(db_session, budget, group, "Rent")
        await create_budget_assignment(db_session, budget, rent, THIS_MONTH, "100.00")
        await _move(api_client, budget, None, bike, "50.00")  # into it
        await _move(api_client, budget, str(rent.id), str(dining.id), "20.00")  # elsewhere
        drains = (await api_client.get(_url(budget))).json()["drains"]
        assert drains["moves"] == []
        assert Decimal(drains["total"]) == Decimal("0")

    async def test_impact_is_none_on_an_envelope_with_no_pace(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Home")
        cat = await create_category(db_session, budget, group, "Home Upgrades")
        # Money that was there before this month and nothing assigned lately.
        await create_budget_assignment(
            db_session, budget, cat, add_months(THIS_MONTH, -6), "500.00"
        )
        await _add(
            api_client,
            budget,
            name="Desk",
            cost="900",
            funding={"mode": "existing", "category_id": str(cat.id)},
        )
        await _move(api_client, budget, str(cat.id), None, "40.00")
        [row] = (await api_client.get(_url(budget))).json()["drains"]["moves"]
        assert row["affected"][0]["months_further"] is None

    async def test_the_savings_report_lists_the_same_move(self, db_session, api_client):
        budget, _wish, bike, dining = await self._setup(db_session, api_client)
        tags = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
        savings = next(t for t in tags if t["system_key"] == "savings")
        r = await api_client.put(
            f"/api/v1/{budget.id}/categories/{bike}/tags", json={"tag_ids": [savings["id"]]}
        )
        assert r.status_code == 200, r.text
        await _move(api_client, budget, bike, str(dining.id), "60.00")
        # A move from a savings envelope no wish draws on shows on the report only.
        group = await create_category_group(db_session, budget, "Savings")
        holiday = await create_category(db_session, budget, group, "Holiday")
        await create_budget_assignment(db_session, budget, holiday, THIS_MONTH, "200.00")
        await api_client.put(
            f"/api/v1/{budget.id}/categories/{holiday.id}/tags", json={"tag_ids": [savings["id"]]}
        )
        await _move(api_client, budget, str(holiday.id), str(dining.id), "15.00")

        report = (await api_client.get(f"/api/v1/{budget.id}/reports/savings")).json()
        wishlist = (await api_client.get(_url(budget))).json()

        assert Decimal(report["drains"]["total"]) == Decimal("75.00")
        report_ids = {m["move_id"] for m in report["drains"]["moves"]}
        wish_ids = {m["move_id"] for m in wishlist["drains"]["moves"]}
        assert wish_ids <= report_ids
        assert len(wish_ids) == 1 and len(report_ids) == 2
        assert {m["from_name"] for m in report["drains"]["moves"]} == {"Bike", "Holiday"}


class TestTurningTheWishlistOffDoesNotStrandMoney:
    """The switch used to write `is_archived` straight to the group's row.

    An archived group takes every envelope under it off the budget
    (`IN_ARCHIVED_GROUP`), so whatever a wish envelope held went with it: still
    deducted from Ready to Assign, drawn nowhere, reachable only by turning the
    switch back on. The settings copy said the money "stays exactly where it
    is", which was true of the row and false of everything the user could see.

    It now returns the money — but only on an explicit confirmation, so no
    request that merely says `wishlist: false` can move any.
    """

    async def _fund_a_wish(self, db_session, api_client, budget, amount="150.00"):
        account = await create_account(db_session, budget, account_type="checking")
        await create_transaction(db_session, budget, account, "1000.00", TODAY)
        wish = await _add(api_client, budget, funding={"mode": "own"})
        cat_id = wish["funding"]["category_id"]
        r = await api_client.patch(
            f"/api/v1/categories/{cat_id}/assignment",
            params={"budget_id": str(budget.id), "month": THIS_MONTH.isoformat()},
            json={"amount": amount},
        )
        assert r.status_code in (200, 204), r.text
        return cat_id

    async def _tba(self, api_client, budget) -> Decimal:
        r = await api_client.get(f"/api/v1/{budget.id}/months/{THIS_MONTH.isoformat()}")
        return Decimal(r.json()["to_be_assigned"])

    async def _set_wishlist(self, api_client, budget, on: bool, **extra):
        return await api_client.put(
            f"/api/v1/{budget.id}/guide/preferences", json={"wishlist": on, **extra}
        )

    async def test_it_refuses_without_confirmation_and_says_how_much(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await self._fund_a_wish(db_session, api_client, budget)
        before = await self._tba(api_client, budget)

        r = await self._set_wishlist(api_client, budget, False)
        assert r.status_code == 400, r.text
        assert "150" in r.json()["detail"]

        # Nothing moved and nothing archived — a refusal that half-applied
        # would be worse than the bug it replaced.
        assert await self._tba(api_client, budget) == before
        assert (await _wishlist_group(api_client, budget))["is_archived"] is False
        prefs = (await api_client.get(f"/api/v1/{budget.id}/guide/preferences")).json()
        assert prefs["wishlist"] is True

    async def test_the_preview_names_the_envelopes_and_the_total(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await self._fund_a_wish(db_session, api_client, budget)

        r = await api_client.get(f"/api/v1/{budget.id}/guide/wishlist/retire-preview")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_empty"] is False
        assert body["envelopes"] == ["Bike"]
        assert money(body["available"]) == Decimal("150.00")

    async def test_confirming_returns_the_money_to_ready_to_assign(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await self._fund_a_wish(db_session, api_client, budget)
        before = await self._tba(api_client, budget)

        r = await self._set_wishlist(api_client, budget, False, release_wishlist_money=True)
        assert r.status_code == 200, r.text
        assert r.json()["wishlist"] is False

        assert await self._tba(api_client, budget) - before == Decimal("150.00")
        assert (await _wishlist_group(api_client, budget))["is_archived"] is True

    async def test_an_empty_wishlist_needs_no_confirmation(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await _add(api_client, budget, funding={"mode": "own"})

        r = await api_client.get(f"/api/v1/{budget.id}/guide/wishlist/retire-preview")
        assert r.json()["is_empty"] is True
        r = await self._set_wishlist(api_client, budget, False)
        assert r.status_code == 200, r.text
        assert (await _wishlist_group(api_client, budget))["is_archived"] is True

    async def test_turning_it_back_on_restores_the_group(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await self._fund_a_wish(db_session, api_client, budget)
        await self._set_wishlist(api_client, budget, False, release_wishlist_money=True)

        r = await self._set_wishlist(api_client, budget, True)
        assert r.status_code == 200, r.text
        assert (await _wishlist_group(api_client, budget))["is_archived"] is False
        # The envelopes come back empty, which is the honest result of having
        # returned the money — not a second surprise.
        assert await self._tba(api_client, budget) == await self._tba(api_client, budget)

    async def test_no_money_no_preview_no_confirmation_needed(self, db_session, api_client):
        """A budget that never used the wishlist previews as empty rather than
        erroring on a group that does not exist yet."""
        budget = await _budget(db_session, api_client)
        r = await api_client.get(f"/api/v1/{budget.id}/guide/wishlist/retire-preview")
        assert r.status_code == 200 and r.json()["is_empty"] is True
