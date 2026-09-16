"""The Guide's "Setting money aside" examples, checked on paper.

Every figure the tab shows is served by the functions the reports run; the
expectations here are written by hand, never derived, so the arithmetic is the
thing under test.
"""

from .factories import create_budget

CHECKING = {"classification": "asset", "on_budget": True, "counts_as_savings": True}
#: Cascade Point HYSA: off budget, counts as savings.
HYSA = {"classification": "asset", "on_budget": False, "counts_as_savings": True}


def _general_savings_month(kind: str) -> list[dict]:
    """One month in General Savings: the same three moves either way."""
    return [
        {"label": "Assign", "kind": "assign", "category": kind, "amount": "500"},
        {
            "label": "Car repair",
            "kind": "transaction",
            "account": CHECKING,
            "direction": "out",
            "category": kind,
            "amount": "120",
        },
        {
            "label": "To Cascade Point HYSA",
            "kind": "transfer",
            "account": CHECKING,
            "to_account": HYSA,
            "category": kind,
            "amount": "300",
        },
    ]


async def _month(db_session, api_client, kind: str) -> dict:
    budget = await create_budget(db_session, api_client.test_user)
    r = await api_client.post(
        f"/api/v1/{budget.id}/guide/money-moves/month",
        json={"moves": _general_savings_month(kind)},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _row(body: dict, i: int) -> tuple[list[str], int]:
    """The on-budget classes of a row, and what it held."""
    e = body["rows"][i]["explanation"]
    return [leg["cls"] for leg in e["legs"] if leg["on_budget"]], e["held"]


class TestSavingsModesMonth:
    async def test_sent_out_saves_the_repair_and_the_transfer(self, db_session, api_client):
        body = await _month(db_session, api_client, "savings_sent")
        assert _row(body, 0) == ([], 0)
        assert _row(body, 1) == (["savings"], 0)
        assert _row(body, 2) == (["savings"], 0)
        figures = body["figures"]
        assert (figures["savings_moved"], figures["savings_held"], figures["savings"]) == (
            420,
            0,
            420,
        )
        assert figures["spending"] == 0

    async def test_kept_here_saves_what_was_assigned_less_the_repair(self, db_session, api_client):
        body = await _month(db_session, api_client, "savings_kept")
        assert _row(body, 0) == ([], 500)
        assert _row(body, 1) == (["spending"], -120)
        assert _row(body, 2) == (["savings"], -300)
        assert body["held"] == 80
        figures = body["figures"]
        assert (figures["savings_moved"], figures["savings_held"], figures["savings"]) == (
            300,
            80,
            380,
        )
        assert figures["spending"] == 120

    async def test_the_assign_moves_ready_to_assign_into_the_envelope(self, db_session, api_client):
        for kind in ("savings_sent", "savings_kept"):
            terms = (await _month(db_session, api_client, kind))["rows"][0]["explanation"][
                "budget_terms"
            ]
            assert terms == [
                {"term": "ready_to_assign", "delta": -500},
                {"term": "envelope", "delta": 500},
            ]


class TestSpreadExample:
    async def test_the_served_figures_are_the_ones_on_paper(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        r = await api_client.get(f"/api/v1/{budget.id}/guide/examples/spread")
        assert r.status_code == 200, r.text
        # $2,000 a month and a $2,400 yearly bill: as paid $2,800 in the
        # quarter the bill landed, $2,000 otherwise; spread $2,000 + $200.
        assert r.json() == {
            "as_paid_after_bill": 2800,
            "as_paid_otherwise": 2000,
            "spread": 2200,
            "bill_monthly_share": 200,
            "goal_months": 3,
            "goal_as_paid_after_bill": 8400,
            "goal_as_paid_otherwise": 6000,
            "goal_spread": 6600,
        }
