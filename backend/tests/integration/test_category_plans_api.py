"""Category plans: document CRUD, draft-permissive storage, and apply-targets.

Storage is deliberately permissive (autosave persists half-typed rows) and
apply is deliberately strict-but-reporting: rows it cannot act on are
classified and counted, never 500s. The draft-permissiveness tests are a
spec, not an accident — tightening PUT validation breaks autosave.
"""

import uuid

from .factories import create_budget, create_category, create_category_group, create_user


async def _budget(db_session, api_client):
    return await create_budget(db_session, api_client.test_user)


def _url(budget) -> str:
    return f"/api/v1/{budget.id}/category-plans"


def _item(name: str, cents: int | None, due: int | None = None, cat: str | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "category_id": cat,
        "name": name,
        "due_day": due,
        "amount_cents": cents,
    }


def _paycheck(*items: dict, income: int | None = None) -> dict:
    return {"id": str(uuid.uuid4()), "income_override_cents": income, "items": list(items)}


def _payload(*paychecks: dict, income: int = 520000, cadence: str = "biweekly") -> dict:
    return {
        "schema_version": 1,
        "monthly_income_cents": income,
        "cadence": cadence,
        "paycheck_count_override": None,
        "paychecks": list(paychecks) or [_paycheck(), _paycheck()],
    }


async def _create(api_client, budget, **body):
    r = await api_client.post(_url(budget), json=body)
    assert r.status_code == 201, r.text
    return r.json()


class TestCrud:
    async def test_create_with_defaults(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        plan = await _create(api_client, budget)
        assert plan["name"] == "Plan 1"
        assert plan["payload"]["schema_version"] == 1
        assert plan["payload"]["cadence"] == "biweekly"
        # The default doc matches its cadence: biweekly means two paychecks.
        assert len(plan["payload"]["paychecks"]) == 2
        assert (await _create(api_client, budget))["name"] == "Plan 2"

    async def test_cents_round_trip_exactly(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        doc = _payload(_paycheck(_item("Rent", 100001, due=1)), _paycheck())
        plan = await _create(api_client, budget, payload=doc)
        assert plan["payload"]["paychecks"][0]["items"][0]["amount_cents"] == 100001
        r = await api_client.get(f"{_url(budget)}/{plan['id']}")
        assert r.status_code == 200
        assert r.json()["payload"]["paychecks"][0]["items"][0]["amount_cents"] == 100001

    async def test_list_is_summaries(self, db_session, api_client):
        # Order is (created_at, name); in one test transaction now() ties, so
        # the names here agree with both orders rather than asserting the tie.
        budget = await _budget(db_session, api_client)
        await _create(api_client, budget, name="Aggressive savings")
        await _create(api_client, budget, name="Tight month")
        r = await api_client.get(_url(budget))
        assert r.status_code == 200
        rows = r.json()
        assert [p["name"] for p in rows] == ["Aggressive savings", "Tight month"]
        assert "payload" not in rows[0]

    async def test_put_replaces_the_document(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        plan = await _create(api_client, budget)
        doc = _payload(_paycheck(_item("Groceries", 45000)), _paycheck(), income=610000)
        r = await api_client.put(f"{_url(budget)}/{plan['id']}", json={"payload": doc})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["payload"]["monthly_income_cents"] == 610000
        assert body["payload"]["paychecks"][0]["items"][0]["name"] == "Groceries"

    async def test_rename(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        plan = await _create(api_client, budget, name="Draft")
        await _create(api_client, budget, name="Final")
        r = await api_client.patch(f"{_url(budget)}/{plan['id']}", json={"name": "Final"})
        assert r.status_code == 409
        r = await api_client.patch(f"{_url(budget)}/{plan['id']}", json={"name": "draft"})
        assert r.status_code == 200 and r.json()["name"] == "draft"

    async def test_duplicate_copies_the_document(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        doc = _payload(_paycheck(_item("Internet", 8000, due=15)), _paycheck())
        plan = await _create(api_client, budget, name="Base", payload=doc)
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/duplicate", json={})
        assert r.status_code == 201, r.text
        copy = r.json()
        assert copy["name"] == "Base (copy)"
        assert copy["id"] != plan["id"]
        assert copy["payload"] == plan["payload"]
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/duplicate", json={})
        assert r.status_code == 201 and r.json()["name"] == "Base (copy 2)"

    async def test_delete(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        plan = await _create(api_client, budget)
        r = await api_client.delete(f"{_url(budget)}/{plan['id']}")
        assert r.status_code == 204
        r = await api_client.get(f"{_url(budget)}/{plan['id']}")
        assert r.status_code == 404


class TestValidation:
    async def _put(self, api_client, budget, plan, doc):
        return await api_client.put(f"{_url(budget)}/{plan['id']}", json={"payload": doc})

    async def test_shape_bounds_are_422(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        plan = await _create(api_client, budget)
        bad_docs = [
            _payload(cadence="fortnightly"),
            _payload(_paycheck(_item("Rent", 1000, due=0)), _paycheck()),
            _payload(_paycheck(_item("Rent", 1000, due=32)), _paycheck()),
            _payload(_paycheck(_item("Rent", -1)), _paycheck()),
            {**_payload(), "paychecks": []},
            {**_payload(), "paychecks": [_paycheck() for _ in range(11)]},
            {**_payload(), "schema_version": 2},
            {**_payload(), "monthly_income_cents": -1},
        ]
        for doc in bad_docs:
            r = await self._put(api_client, budget, plan, doc)
            assert r.status_code == 422, f"{doc} was accepted"

    async def test_duplicate_ids_are_422(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        plan = await _create(api_client, budget)
        twin = _paycheck()
        r = await self._put(api_client, budget, plan, _payload(twin, {**twin}))
        assert r.status_code == 422
        item = _item("Rent", 1000)
        r = await self._put(
            api_client, budget, plan, _payload(_paycheck(item), _paycheck({**item}))
        )
        assert r.status_code == 422

    async def test_draft_rows_are_a_spec_not_an_accident(self, db_session, api_client):
        """Autosave persists half-typed rows: empty name, missing amount, and
        a dangling category link must all store. Tightening this breaks the
        planner mid-keystroke."""
        budget = await _budget(db_session, api_client)
        plan = await _create(api_client, budget)
        doc = _payload(
            _paycheck(
                _item("", 12000),
                _item("Utilities", None),
                _item("Old link", 5000, cat=str(uuid.uuid4())),
            ),
            _paycheck(),
        )
        r = await self._put(api_client, budget, plan, doc)
        assert r.status_code == 200, r.text

    async def test_plan_cap_is_409(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        for _ in range(20):
            await _create(api_client, budget)
        r = await api_client.post(_url(budget), json={})
        assert r.status_code == 409
        r = await api_client.post(_url(budget), json={"name": "One more"})
        assert r.status_code == 409

    async def test_name_collision_is_409(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        await _create(api_client, budget, name="August")
        r = await api_client.post(_url(budget), json={"name": "August"})
        assert r.status_code == 409


async def _categories(api_client, budget):
    r = await api_client.get(f"/api/v1/{budget.id}/categories?include_archived=true")
    assert r.status_code == 200
    return r.json()


async def _groups(api_client, budget):
    r = await api_client.get(f"/api/v1/{budget.id}/category-groups?include_archived=true")
    assert r.status_code == 200
    return r.json()


async def _targets(api_client, budget):
    r = await api_client.get(f"/api/v1/{budget.id}/targets")
    assert r.status_code == 200
    return {t["category_id"]: t for t in r.json()}


class TestApplyTargets:
    async def test_free_rows_create_categories_in_planned(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        doc = _payload(
            _paycheck(_item("Rent", 145000, due=1)), _paycheck(_item("Groceries", 45000))
        )
        plan = await _create(api_client, budget, payload=doc)
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/apply-targets", json={})
        assert r.status_code == 200, r.text
        report = r.json()
        assert report["categories_created"] == 2
        assert report["targets_set"] == 0 and report["targets_updated"] == 0

        planned = next(g for g in await _groups(api_client, budget) if g["name"] == "Planned")
        cats = {c["name"]: c for c in await _categories(api_client, budget)}
        assert cats["Rent"]["category_group_id"] == planned["id"]
        targets = await _targets(api_client, budget)
        rent_target = targets[cats["Rent"]["id"]]
        assert rent_target["target_type"] == "monthly_funding"
        assert rent_target["target_amount"] == 1450.0

    async def test_adopts_an_existing_planned_group(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        mine = await create_category_group(db_session, budget, "Planned")
        plan = await _create(
            api_client, budget, payload=_payload(_paycheck(_item("Rent", 145000)), _paycheck())
        )
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/apply-targets", json={})
        assert r.status_code == 200
        groups = [g for g in await _groups(api_client, budget) if g["name"] == "Planned"]
        assert [g["id"] for g in groups] == [str(mine.id)]

    async def test_free_row_adopts_a_same_named_category(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        plan = await _create(
            api_client, budget, payload=_payload(_paycheck(_item("groceries", 45000)), _paycheck())
        )
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/apply-targets", json={})
        assert r.status_code == 200, r.text
        report = r.json()
        assert report["categories_created"] == 0 and report["targets_set"] == 1
        # The row is now linked, with the canonical name as its snapshot…
        item = report["plan"]["payload"]["paychecks"][0]["items"][0]
        assert item["category_id"] == str(groceries.id)
        assert item["name"] == "Groceries"
        # …and no second "Groceries" appeared anywhere.
        assert (
            len(
                [
                    c
                    for c in await _categories(api_client, budget)
                    if c["name"].lower() == "groceries"
                ]
            )
            == 1
        )

    async def test_updates_monthly_and_keeps_other_target_types(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Bills")
        internet = await create_category(db_session, budget, group, "Internet")
        vacation = await create_category(db_session, budget, group, "Vacation")
        r = await api_client.post(
            f"/api/v1/categories/{internet.id}/target",
            json={"target_type": "monthly_funding", "target_amount": "60.00"},
        )
        assert r.status_code == 201
        r = await api_client.post(
            f"/api/v1/categories/{vacation.id}/target",
            json={"target_type": "savings_balance", "target_amount": "3000.00"},
        )
        assert r.status_code == 201

        doc = _payload(
            _paycheck(
                _item("Internet", 8000, cat=str(internet.id)),
                _item("Vacation", 20000, cat=str(vacation.id)),
            ),
            _paycheck(),
        )
        plan = await _create(api_client, budget, payload=doc)
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/apply-targets", json={})
        assert r.status_code == 200
        report = r.json()
        assert report["targets_updated"] == 1
        assert report["skipped_existing_type"] == 1
        kept = next(e for e in report["entries"] if e["kind"] == "skip_existing_type")
        assert kept["existing_target_type"] == "savings_balance"

        targets = await _targets(api_client, budget)
        assert targets[str(internet.id)]["target_amount"] == 80.0
        assert targets[str(vacation.id)]["target_type"] == "savings_balance"
        assert targets[str(vacation.id)]["target_amount"] == 3000.0

    async def test_rows_naming_one_category_are_summed(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        doc = _payload(
            _paycheck(_item("Groceries", 30000, cat=str(groceries.id))),
            _paycheck(
                _item("Groceries", 25000, cat=str(groceries.id)),
                # Free-form twins merge into one created category too.
                _item("Car fund", 10000),
                _item("car fund", 5000),
            ),
        )
        plan = await _create(api_client, budget, payload=doc)
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/apply-targets", json={})
        assert r.status_code == 200
        report = r.json()
        assert report["targets_set"] == 1 and report["categories_created"] == 1
        targets = await _targets(api_client, budget)
        assert targets[str(groceries.id)]["target_amount"] == 550.0
        car = next(c for c in await _categories(api_client, budget) if c["name"] == "Car fund")
        assert targets[car["id"]]["target_amount"] == 150.0

    async def test_drafts_and_invalid_links_are_reported_not_applied(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        stranger = await create_user(db_session)
        their_budget = await create_budget(db_session, stranger)
        their_group = await create_category_group(db_session, their_budget, "Their Group")
        theirs = await create_category(db_session, their_budget, their_group, "Their Category")
        doc = _payload(
            _paycheck(
                _item("", 12000),
                _item("Utilities", None),
                _item("Gone", 5000, cat=str(uuid.uuid4())),
                _item("Not mine", 5000, cat=str(theirs.id)),
            ),
            _paycheck(),
        )
        plan = await _create(api_client, budget, payload=doc)
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/apply-targets", json={})
        assert r.status_code == 200, r.text
        report = r.json()
        assert report["skipped_draft"] == 2
        assert report["skipped_invalid_link"] == 2
        assert report["categories_created"] == 0
        assert await _targets(api_client, budget) == {}

    async def test_second_apply_updates_instead_of_duplicating(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        doc = _payload(_paycheck(_item("Rent", 145000)), _paycheck())
        plan = await _create(api_client, budget, payload=doc)
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/apply-targets", json={})
        assert r.json()["categories_created"] == 1
        # The write-back linked the row, so applying again is an update.
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/apply-targets", json={})
        report = r.json()
        assert report["categories_created"] == 0
        assert report["targets_updated"] == 1
        assert len([c for c in await _categories(api_client, budget) if c["name"] == "Rent"]) == 1

    async def test_preview_mutates_nothing(self, db_session, api_client):
        budget = await _budget(db_session, api_client)
        doc = _payload(_paycheck(_item("Rent", 145000)), _paycheck())
        plan = await _create(api_client, budget, payload=doc)
        r = await api_client.post(f"{_url(budget)}/{plan['id']}/apply-targets/preview", json={})
        assert r.status_code == 200, r.text
        report = r.json()
        assert report["categories_created"] == 1
        assert "plan" not in report
        assert [g for g in await _groups(api_client, budget) if g["name"] == "Planned"] == []
        assert await _categories(api_client, budget) == []
        # The row is still free-form: nothing was written back.
        r = await api_client.get(f"{_url(budget)}/{plan['id']}")
        assert r.json()["payload"]["paychecks"][0]["items"][0]["category_id"] is None


class TestIsolation:
    async def test_foreign_budget_is_404_everywhere(self, db_session, api_client):
        stranger = await create_user(db_session)
        theirs = await create_budget(db_session, stranger)
        url = _url(theirs)
        fake = uuid.uuid4()
        checks = [
            ("get", url, None),
            ("post", url, {}),
            ("get", f"{url}/{fake}", None),
            ("put", f"{url}/{fake}", {"payload": _payload()}),
            ("patch", f"{url}/{fake}", {"name": "Mine now"}),
            ("post", f"{url}/{fake}/duplicate", {}),
            ("delete", f"{url}/{fake}", None),
            ("post", f"{url}/{fake}/apply-targets/preview", {}),
            ("post", f"{url}/{fake}/apply-targets", {}),
        ]
        for method, path, body in checks:
            r = await api_client.request(method.upper(), path, json=body)
            assert r.status_code == 404, f"{method} {path} -> {r.status_code}"

    async def test_plan_id_is_scoped_to_its_budget(self, db_session, api_client):
        budget_a = await _budget(db_session, api_client)
        budget_b = await create_budget(db_session, api_client.test_user, "Second Budget")
        plan = await _create(api_client, budget_a)
        r = await api_client.get(f"{_url(budget_b)}/{plan['id']}")
        assert r.status_code == 404
