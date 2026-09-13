"""The Guide's "How money counts" endpoints.

What the answers ARE is pinned elsewhere — classes and budget terms against
real rows in `test_money_moves_agreement.py`. Here: the wire shape, the cases
the tab leads with, and a month whose figures are checked on paper.
"""

import pytest

from igab.domain.activity_class import RULES

from .factories import create_budget

CHECKING = {"classification": "asset", "on_budget": True, "counts_as_savings": True}
CARD = {"classification": "liability", "on_budget": True, "counts_as_savings": True}
BROKERAGE = {"classification": "asset", "on_budget": False, "counts_as_savings": True}
CAR = {"classification": "asset", "on_budget": False, "counts_as_savings": False}
MORTGAGE = {"classification": "liability", "on_budget": False, "counts_as_savings": True}


def _transfer(frm, to, amount="1000", category="none"):
    return {
        "kind": "transfer",
        "account": frm,
        "to_account": to,
        "amount": amount,
        "category": category,
    }


def _transaction(account, direction, amount="1000", category="none"):
    return {
        "kind": "transaction",
        "account": account,
        "direction": direction,
        "amount": amount,
        "category": category,
    }


async def _explain(api_client, budget, body):
    r = await api_client.post(f"/api/v1/{budget.id}/guide/money-moves/explain", json=body)
    assert r.status_code == 200, r.text
    return r.json()


class TestMoneyRules:
    async def test_the_ladder_is_the_shipped_rules_then_the_default(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        r = await api_client.get(f"/api/v1/{budget.id}/guide/money-rules")
        assert r.status_code == 200, r.text
        body = r.json()
        rules = body["rules"]
        assert [rule["reason"] for rule in rules[:-1]] == [reason.value for _, _, reason in RULES]
        assert rules[-1] == {
            "position": len(RULES) + 1,
            "cls": "spending",
            "class_label": "Spending",
            "reason": "default_spending",
            "reason_text": "it is ordinary spending from a budget account",
            "tag_key": None,
            "is_default": True,
        }
        assert [r["tag_key"] for r in rules if r["tag_key"]] == ["savings", "debt_principal"]
        assert body["planned_spend_tag_keys"] == ["savings"]
        families = {f["key"]: f["classes"] for f in body["report_families"]}
        assert families["cost_of_living"] == ["spending", "debt_principal"]

    async def test_every_shape_says_what_money_in_and_out_count_as(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        shapes = {
            s["key"]: s
            for s in (await api_client.get(f"/api/v1/{budget.id}/guide/money-rules")).json()[
                "shapes"
            ]
        }
        assert set(shapes) == {
            "budget_cash",
            "budget_card",
            "tracked_savings",
            "tracked_asset",
            "tracked_debt",
        }

        def on_budget_class(example):
            return [leg["cls"] for leg in example["explanation"]["legs"] if leg["on_budget"]]

        assert on_budget_class(shapes["tracked_savings"]["money_in"]) == ["savings"]
        assert on_budget_class(shapes["tracked_asset"]["money_in"]) == ["spending"]
        assert on_budget_class(shapes["tracked_asset"]["money_out"]) == ["income"]
        assert on_budget_class(shapes["tracked_debt"]["money_in"]) == ["debt_principal"]
        assert shapes["tracked_asset"]["counts_as_savings"] is False
        assert shapes["budget_card"]["counts_as_savings"] is None


class TestExplain:
    async def test_selling_a_car_into_checking_is_income_ready_to_assign(
        self, db_session, api_client
    ):
        budget = await create_budget(db_session, api_client.test_user)
        body = await _explain(api_client, budget, _transfer(CAR, CHECKING))
        checking_leg = next(leg for leg in body["legs"] if leg["on_budget"])
        car_leg = next(leg for leg in body["legs"] if not leg["on_budget"])
        assert checking_leg["cls"] == "income"
        assert checking_leg["counted_in"] == ["income"]
        assert car_leg["cls"] == "transfer_internal" and car_leg["counted_in"] == []
        assert body["budget_terms"] == [{"term": "ready_to_assign", "delta": 1000}]
        assert body["category_role"] == "to"
        assert body["net_worth_delta"] == 0
        assert body["figures"]["income"] == 1000
        assert body["assumption"]

    async def test_the_same_sale_from_a_savings_account_un_saves(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        body = await _explain(api_client, budget, _transfer(BROKERAGE, CHECKING))
        checking_leg = next(leg for leg in body["legs"] if leg["on_budget"])
        assert checking_leg["cls"] == "savings"
        assert body["figures"]["savings"] == -1000

    async def test_checking_to_an_on_budget_hysa_is_a_transfer_counted_nowhere(
        self, db_session, api_client
    ):
        budget = await create_budget(db_session, api_client.test_user)
        body = await _explain(
            api_client, budget, _transfer(CHECKING, CHECKING, category="ordinary")
        )
        assert [leg["cls"] for leg in body["legs"]] == ["transfer_internal"] * 2
        assert all(leg["counted_in"] == [] for leg in body["legs"])
        assert body["budget_terms"] == []
        assert body["category_role"] is None
        assert body["category_applied"] is False
        assert body["figures"]["savings_rate"] is None

    async def test_a_savings_tagged_flight_is_saving_and_spent_against_the_plan(
        self, db_session, api_client
    ):
        budget = await create_budget(db_session, api_client.test_user)
        body = await _explain(
            api_client, budget, _transaction(CHECKING, "out", "250", category="savings")
        )
        (leg,) = body["legs"]
        assert leg["cls"] == "savings" and leg["reason"] == "tagged_savings"
        assert leg["planned_spend_by_tag"] is True
        assert body["budget_terms"] == [{"term": "envelope", "delta": -250}]
        assert body["net_worth_delta"] == -250

    @pytest.mark.parametrize(
        "body",
        [
            _transfer(CHECKING, None),
            {**_transaction(CHECKING, "in"), "to_account": BROKERAGE},
            _transaction(CHECKING, "sideways"),
            _transaction(CHECKING, "in", amount="0"),
            _transaction(CHECKING, "in", category="groceries"),
        ],
    )
    async def test_a_move_that_does_not_fit_its_kind_is_refused(self, db_session, api_client, body):
        budget = await create_budget(db_session, api_client.test_user)
        r = await api_client.post(f"/api/v1/{budget.id}/guide/money-moves/explain", json=body)
        assert r.status_code == 422


#: The Guide's worked month, figures checked by hand.
WORKED_MONTH = [
    ("Paycheck from Northwind Payserv", _transaction(CHECKING, "in", "6000", "income")),
    ("Harborstone mortgage payment", _transfer(CHECKING, MORTGAGE, "1800")),
    ("To the brokerage", _transfer(CHECKING, BROKERAGE, "500")),
    ("Flight from Vacation", _transaction(CHECKING, "out", "250", "savings")),
    ("To Cascade Point HYSA", _transfer(CHECKING, CHECKING, "400")),
    ("Sapphire Visa payment", _transfer(CHECKING, CARD, "900")),
    ("Everyday spending", _transaction(CHECKING, "out", "2300", "ordinary")),
    ("Dividend in the brokerage", _transaction(BROKERAGE, "in", "35")),
    ("Sold the car", _transfer(CAR, CHECKING, "4500")),
]


class TestMonth:
    async def test_the_worked_month_adds_up(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        r = await api_client.post(
            f"/api/v1/{budget.id}/guide/money-moves/month",
            json={"moves": [{**move, "label": label} for label, move in WORKED_MONTH]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert [row["label"] for row in body["rows"]] == [label for label, _ in WORKED_MONTH]
        # Income 6,000 + 4,500 car; saving 500 + 250; principal the whole 1,800.
        assert body["class_totals"] == {
            "income": 10500,
            "debt_principal": -1800,
            "savings": -750,
            "transfer_internal": 0,
            "spending": -2300,
        }
        figures = body["figures"]
        assert (figures["income"], figures["spending"], figures["savings"]) == (10500, 2300, 750)
        assert figures["cost_of_living"] == 4100
        assert figures["savings_rate"] == pytest.approx(750 / 10500)
        assert figures["savings_rate_with_debt"] == pytest.approx(2550 / 10500)
        dividend = body["rows"][7]["explanation"]["legs"][0]
        assert dividend["cls"] == "investment_return" and dividend["counted_in"] == []

    async def test_an_empty_month_is_refused(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        r = await api_client.post(
            f"/api/v1/{budget.id}/guide/money-moves/month", json={"moves": []}
        )
        assert r.status_code == 422
