"""`payee_of_record_id`: who a split leg was paid to.

A split leg carries no payee of its own — the parent names the shop. The
register lists parents, so it never noticed; but the budget's Activity peek and
the report drills list *legs*, and drew "—" for the Groceries share of a $240
Harborstone Wholesale receipt. Nothing in that list said where the money went,
and clicking it led to a register that has no such row, so it read as a phantom
charge — in Groceries, Misc, and every other envelope the receipt touched.

The server already had the rule (`PAYEE_OF_RECORD`, which reports group by); it
now serves it. Checklist discipline as in test_transfer_counterpart.py: None is
a legal value, so a path that forgets the loader degrades silently to "no
payee" — every serializing path a leg can reach is swept below.
"""

from datetime import date

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
)

TODAY = date(2026, 9, 29)


async def _split_fixture(db_session, user):
    """A $240 split: a payee-less Groceries leg, and a Misc leg that names its
    own payee (an itemised line can), beside a plain row and a payee-less one."""
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    misc = await create_category(db_session, budget, group, "Misc")
    shop = await create_payee(db_session, budget, "Harborstone Wholesale")
    vendor = await create_payee(db_session, budget, "Concession Stand")

    parent = await create_transaction(
        db_session, budget, checking, "-240.00", TODAY, payee=shop, is_split=True
    )
    bare_leg = await create_transaction(
        db_session,
        budget,
        checking,
        "-125.00",
        TODAY,
        category=groceries,
        parent_transaction_id=parent.id,
    )
    named_leg = await create_transaction(
        db_session,
        budget,
        checking,
        "-115.00",
        TODAY,
        category=misc,
        payee=vendor,
        parent_transaction_id=parent.id,
    )
    plain = await create_transaction(
        db_session, budget, checking, "-10.00", TODAY, category=groceries, payee=vendor
    )
    nobody = await create_transaction(db_session, budget, checking, "-5.00", TODAY)
    return budget, checking, groceries, shop, vendor, parent, bare_leg, named_leg, plain, nobody


def _by_id(rows: list[dict]) -> dict[str, dict]:
    return {r["id"]: r for r in rows}


class TestRule:
    async def test_every_shape_through_the_leaf_listing(self, api_client, db_session):
        """The Activity peek's own query: leaf scope, no category filter."""
        (
            budget,
            _,
            _,
            shop,
            vendor,
            parent,
            bare_leg,
            named_leg,
            plain,
            nobody,
        ) = await _split_fixture(db_session, api_client.test_user)
        body = (
            await api_client.get(f"/api/v1/{budget.id}/transactions", params={"scope": "leaf"})
        ).json()
        rows = _by_id(body["transactions"])
        assert rows[str(bare_leg.id)]["payee_id"] is None, "the leg itself still has none"
        assert rows[str(bare_leg.id)]["payee_of_record_id"] == str(shop.id), (
            "a payee-less leg is paid to its parent's payee"
        )
        assert rows[str(named_leg.id)]["payee_of_record_id"] == str(vendor.id), (
            "a leg naming its own payee keeps it — the parent does not override"
        )
        assert rows[str(plain.id)]["payee_of_record_id"] == str(vendor.id)
        assert rows[str(nobody.id)]["payee_of_record_id"] is None, "no payee anywhere is None"
        assert str(parent.id) not in rows, "leaf scope excludes the split parent"

    async def test_parent_edit_reaches_the_leg(self, api_client, db_session):
        """Not a stored copy: retargeting the parent's payee moves the leg's."""
        budget, _, _, _, vendor, parent, bare_leg, *_ = await _split_fixture(
            db_session, api_client.test_user
        )
        resp = await api_client.patch(
            f"/api/v1/transactions/{parent.id}",
            params={"budget_id": str(budget.id)},
            json={"payee_id": str(vendor.id)},
        )
        assert resp.status_code == 200
        body = (
            await api_client.get(f"/api/v1/{budget.id}/transactions", params={"scope": "leaf"})
        ).json()
        assert _by_id(body["transactions"])[str(bare_leg.id)]["payee_of_record_id"] == str(
            vendor.id
        )


class TestListings:
    async def test_category_peek_carries_it(self, api_client, db_session):
        """Exactly the request the budget page's Groceries Activity makes."""
        budget, _, groceries, shop, _, _, bare_leg, *_ = await _split_fixture(
            db_session, api_client.test_user
        )
        body = (
            await api_client.get(
                f"/api/v1/{budget.id}/transactions",
                params={"category_ids": str(groceries.id), "scope": "leaf", "limit": 10},
            )
        ).json()
        rows = _by_id(body["transactions"])
        assert rows[str(bare_leg.id)]["payee_of_record_id"] == str(shop.id)

    async def test_account_register_carries_it(self, api_client, db_session):
        """The register lists parents; there the field is the row's own payee."""
        budget, checking, _, shop, _, parent, *_ = await _split_fixture(
            db_session, api_client.test_user
        )
        rows = _by_id((await api_client.get(f"/api/v1/accounts/{checking.id}/transactions")).json())
        assert rows[str(parent.id)]["payee_of_record_id"] == str(shop.id)

    async def test_single_get_of_a_leg_carries_it(self, api_client, db_session):
        budget, _, _, shop, _, _, bare_leg, *_ = await _split_fixture(
            db_session, api_client.test_user
        )
        body = (
            await api_client.get(
                f"/api/v1/transactions/{bare_leg.id}", params={"budget_id": str(budget.id)}
            )
        ).json()
        assert body["payee_of_record_id"] == str(shop.id)

    async def test_split_lines_carry_it(self, api_client, db_session):
        budget, _, _, shop, vendor, parent, bare_leg, named_leg, *_ = await _split_fixture(
            db_session, api_client.test_user
        )
        rows = _by_id(
            (
                await api_client.get(
                    f"/api/v1/transactions/{parent.id}/splits",
                    params={"budget_id": str(budget.id)},
                )
            ).json()
        )
        assert rows[str(bare_leg.id)]["payee_of_record_id"] == str(shop.id)
        assert rows[str(named_leg.id)]["payee_of_record_id"] == str(vendor.id)


class TestMutatingEndpoints:
    async def test_replacing_split_lines_returns_it(self, api_client, db_session):
        """PUT …/splits updates lines already in the identity map — the case
        where a with_expression loader without populate_existing reads None."""
        budget, _, groceries, shop, vendor, parent, bare_leg, named_leg, *_ = await _split_fixture(
            db_session, api_client.test_user
        )
        resp = await api_client.put(
            f"/api/v1/transactions/{parent.id}/splits",
            params={"budget_id": str(budget.id)},
            json={
                "splits": [
                    {"id": str(bare_leg.id), "amount": "-150.00", "category_id": str(groceries.id)},
                    {
                        "id": str(named_leg.id),
                        "amount": "-60.00",
                        "category_id": str(groceries.id),
                    },
                    {"amount": "-30.00", "category_id": str(groceries.id)},
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        lines = resp.json()
        assert len(lines) == 3
        by_id = _by_id(lines)
        new_line = next(
            line for line in lines if line["id"] not in (str(bare_leg.id), str(named_leg.id))
        )
        assert by_id[str(bare_leg.id)]["payee_of_record_id"] == str(shop.id), "edited in place"
        assert new_line["payee_of_record_id"] == str(shop.id), "created by the PUT"
        assert by_id[str(named_leg.id)]["payee_of_record_id"] == str(vendor.id), (
            "an edit that names no payee leaves the line's own one standing"
        )
