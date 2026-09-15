"""The emergency fund picker: envelopes, accounts and kept elsewhere in one save.

`services/emergency_fund_choice.py` writes the tag membership and modes, the
account flags (turning Counts as savings on where needed) and the Guide's
external rows as one batch — one Cmd+Z.

Invented names and round figures throughout.
"""

from datetime import date
from decimal import Decimal

from igab.domain.dates import month_start
from igab.guide.repo import GuideRepository

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    money,
)

D = Decimal
THIS_MONTH = month_start(date.today())


async def _world(db_session, api_client) -> dict:
    budget = await create_budget(db_session, api_client.test_user)
    goals = await create_category_group(db_session, budget, "Goals")
    w = {
        "budget": budget,
        "fund": await create_category(db_session, budget, goals, "Emergency Fund"),
        "general": await create_category(db_session, budget, goals, "General Savings"),
        "checking": await create_account(db_session, budget, "Harborstone Checking"),
        "reserve": await create_account(
            db_session,
            budget,
            "Harborstone Reserve",
            account_type="savings",
            on_budget=False,
            counts_as_savings=True,
        ),
    }
    await create_budget_assignment(db_session, budget, w["fund"], THIS_MONTH, "2400.00")
    await create_budget_assignment(db_session, budget, w["general"], THIS_MONTH, "300.00")
    await create_transaction(db_session, budget, w["reserve"], "6000.00", THIS_MONTH)
    await db_session.commit()
    return w


def _url(budget) -> str:
    return f"/api/v1/{budget.id}/emergency-fund"


def _body(**over) -> dict:
    return {
        "add_categories": [],
        "remove_categories": [],
        "savings_modes": {},
        "account_ids": [],
        "external": {"declared": False, "amount": None, "note": None},
        **over,
    }


async def _get(api_client, budget) -> dict:
    r = await api_client.get(_url(budget))
    assert r.status_code == 200, r.text
    return r.json()


async def _undo(api_client, budget) -> None:
    r = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
    assert r.status_code == 200, r.text


async def _account(api_client, account) -> dict:
    r = await api_client.get(f"/api/v1/accounts/{account.id}")
    assert r.status_code == 200, r.text
    return r.json()


async def _membership(api_client, budget) -> dict:
    tags = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
    ef = next(t for t in tags if t["system_key"] == "emergency_fund")
    r = await api_client.get(f"/api/v1/{budget.id}/tags/{ef['id']}/membership")
    return {c["name"]: c for c in r.json()["categories"]}


async def test_get_serves_the_fund_and_every_candidate(db_session, api_client):
    w = await _world(db_session, api_client)
    closed = await create_account(
        db_session, w["budget"], "Old Reserve", account_type="savings", on_budget=False
    )
    closed.is_closed = True
    await create_account(
        db_session,
        w["budget"],
        "Cascade Point HYSA",
        account_type="savings",
        on_budget=False,
        counts_as_savings=False,
    )
    await db_session.commit()

    body = await _get(api_client, w["budget"])

    assert body["fund"] == {
        "set_up": False,
        "total": None,
        "categories": [],
        "accounts": [],
        "external": {"declared": False, "amount": None, "as_of": None, "note": None},
    }
    candidates = {c["name"]: c for c in body["account_candidates"]}
    assert set(candidates) == {"Cascade Point HYSA", "Harborstone Reserve"}
    assert candidates["Harborstone Reserve"]["counts_as_savings"] is True
    assert candidates["Cascade Point HYSA"]["counts_as_savings"] is False
    assert money(candidates["Harborstone Reserve"]["balance"]) == D("6000.00")
    assert candidates["Harborstone Reserve"]["member"] is False


async def test_emergency_fund_put_is_one_undo_across_tags_accounts_external(db_session, api_client):
    w = await _world(db_session, api_client)
    budget = w["budget"]

    r = await api_client.put(
        _url(budget),
        json=_body(
            add_categories=[str(w["fund"].id)],
            savings_modes={str(w["fund"].id): "sent_out"},
            account_ids=[str(w["reserve"].id)],
            external={"declared": True, "amount": "1000", "note": "credit union"},
        ),
    )
    assert r.status_code == 200, r.text
    fund = r.json()["fund"]
    assert [(p["name"], money(p["balance"])) for p in fund["categories"]] == [
        ("Emergency Fund", D("2400.00"))
    ]
    assert [p["name"] for p in fund["accounts"]] == ["Harborstone Reserve"]
    assert fund["external"]["declared"] is True
    assert money(fund["external"]["amount"]) == D("1000")
    assert fund["external"]["note"] == "credit union"
    assert money(fund["total"]) == D("9400.00")
    assert (await _membership(api_client, budget))["Emergency Fund"]["savings_mode"] == "sent_out"

    changes = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
    batch = changes[0]["batch_id"]
    assert batch is not None
    assert {c["entity_type"] for c in changes if c["batch_id"] == batch} == {
        "category_tags",
        "category",
        "account",
        "guide_binding",
    }

    await _undo(api_client, budget)

    assert (await _get(api_client, budget))["fund"]["set_up"] is False
    assert (await _account(api_client, w["reserve"]))["counts_toward_emergency_fund"] is False
    rows = await _membership(api_client, budget)
    assert rows["Emergency Fund"]["member"] is False
    assert rows["Emergency Fund"]["savings_mode"] is None
    bindings = await GuideRepository(db_session).bindings(budget.id)
    assert [b for b in bindings if b.concept_key == "emergency_fund"] == []


async def test_emergency_fund_put_turns_on_counts_as_savings(db_session, api_client):
    w = await _world(db_session, api_client)
    budget = w["budget"]
    hysa = await create_account(
        db_session,
        budget,
        "Cascade Point HYSA",
        account_type="savings",
        on_budget=False,
        counts_as_savings=False,
    )
    await create_transaction(db_session, budget, hysa, "500.00", THIS_MONTH)
    await db_session.commit()

    r = await api_client.put(_url(budget), json=_body(account_ids=[str(hysa.id)]))
    assert r.status_code == 200, r.text
    assert [p["name"] for p in r.json()["fund"]["accounts"]] == ["Cascade Point HYSA"]
    account = await _account(api_client, hysa)
    assert (account["counts_as_savings"], account["counts_toward_emergency_fund"]) == (True, True)

    await _undo(api_client, budget)
    account = await _account(api_client, hysa)
    assert (account["counts_as_savings"], account["counts_toward_emergency_fund"]) == (
        False,
        False,
    )


async def test_unchecking_an_account_clears_only_its_flag(db_session, api_client):
    w = await _world(db_session, api_client)
    budget = w["budget"]
    await api_client.put(_url(budget), json=_body(account_ids=[str(w["reserve"].id)]))

    r = await api_client.put(_url(budget), json=_body(account_ids=[]))
    assert r.status_code == 200, r.text
    account = await _account(api_client, w["reserve"])
    assert (account["counts_as_savings"], account["counts_toward_emergency_fund"]) == (True, False)


async def test_emergency_fund_put_refuses_non_candidates(db_session, api_client):
    w = await _world(db_session, api_client)
    budget = w["budget"]
    other = await create_budget(db_session, api_client.test_user)
    stray = await create_account(
        db_session, other, "Northwind Reserve", account_type="savings", on_budget=False
    )
    await db_session.commit()

    for refused in (w["checking"], stray):
        r = await api_client.put(
            _url(budget),
            json=_body(
                add_categories=[str(w["fund"].id)],
                account_ids=[str(w["reserve"].id), str(refused.id)],
            ),
        )
        assert r.status_code == 422, r.text

    assert (await _get(api_client, budget))["fund"]["set_up"] is False, "nothing written"
    assert (await _account(api_client, w["reserve"]))["counts_toward_emergency_fund"] is False


async def test_a_negative_kept_elsewhere_amount_is_refused(db_session, api_client):
    w = await _world(db_session, api_client)
    r = await api_client.put(
        _url(w["budget"]),
        json=_body(external={"declared": True, "amount": "-5", "note": None}),
    )
    assert r.status_code == 422, r.text


async def test_reverse_order_undo_chain(db_session, api_client):
    """An inspector tag edit, then a picker save; undoing twice walks back
    through both, newest first."""
    w = await _world(db_session, api_client)
    budget = w["budget"]
    tags = (await api_client.get(f"/api/v1/{budget.id}/tags")).json()
    ef = next(t for t in tags if t["system_key"] == "emergency_fund")

    r = await api_client.put(
        f"/api/v1/{budget.id}/categories/{w['fund'].id}/tags", json={"tag_ids": [ef["id"]]}
    )
    assert r.status_code == 200, r.text
    r = await api_client.put(
        _url(budget),
        json=_body(
            add_categories=[str(w["general"].id)],
            account_ids=[str(w["reserve"].id)],
            external={"declared": True, "amount": "500", "note": None},
        ),
    )
    assert r.status_code == 200, r.text
    assert money((await _get(api_client, budget))["fund"]["total"]) == D("9200.00")

    await _undo(api_client, budget)
    fund = (await _get(api_client, budget))["fund"]
    assert [p["name"] for p in fund["categories"]] == ["Emergency Fund"]
    assert fund["accounts"] == []
    assert fund["external"]["declared"] is False
    assert money(fund["total"]) == D("2400.00")

    await _undo(api_client, budget)
    assert (await _get(api_client, budget))["fund"]["set_up"] is False


async def test_a_dismissal_survives_only_when_nothing_is_chosen(db_session, api_client):
    w = await _world(db_session, api_client)
    budget = w["budget"]
    r = await api_client.put(
        f"/api/v1/{budget.id}/guide/bindings/emergency_fund", json={"mode": "dismissed"}
    )
    assert r.status_code == 204, r.text

    async def modes() -> list[str]:
        rows = await GuideRepository(db_session).bindings(budget.id)
        return sorted(b.mode for b in rows if b.concept_key == "emergency_fund")

    await api_client.put(_url(budget), json=_body())
    assert await modes() == ["dismissed"]

    await api_client.put(_url(budget), json=_body(add_categories=[str(w["fund"].id)]))
    assert await modes() == [], "choosing asks the Guide to track it again"


async def test_an_unchanged_declaration_records_nothing(db_session, api_client):
    w = await _world(db_session, api_client)
    budget = w["budget"]
    body = _body(external={"declared": True, "amount": "1000.00", "note": "credit union"})
    await api_client.put(_url(budget), json=body)
    before = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]

    body["external"]["amount"] = "1000"
    r = await api_client.put(_url(budget), json=body)
    assert r.status_code == 200, r.text

    after = (await api_client.get(f"/api/v1/{budget.id}/changes")).json()["changes"]
    assert len(after) == len(before)


async def test_a_declared_amount_undoes_from_the_guide_sheet_too(db_session, api_client):
    """Binding rows are dumped as the database stores them (Numeric(19, 4)):
    a figure sent as "4500" was recorded as "4500" and read back as
    "4500.0000", and undo refused it as changed since."""
    w = await _world(db_session, api_client)
    budget = w["budget"]
    r = await api_client.put(
        f"/api/v1/{budget.id}/guide/bindings/hsa",
        json={"mode": "manual", "entity_ids": {}, "external": True, "external_amount": "4500"},
    )
    assert r.status_code == 204, r.text

    await _undo(api_client, budget)
    rows = await GuideRepository(db_session).bindings(budget.id)
    assert [b for b in rows if b.concept_key == "hsa"] == []
