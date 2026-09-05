"""Taking back a bulk assign, through the endpoints the browser calls.

The report: "I couldn't properly undo the auto assignment — it assigned all
of the amounts and then when I hit undo, none of the amounts went back."

None of them did. A bulk assign and Cover Overspending write one budget move
per envelope under one batch id, and `undo_batch` was strictly all-or-nothing
with a per-row staleness check — so hand-editing a single envelope afterwards
(the obvious first reaction to a wrong bulk assign) made the whole operation
permanently un-undoable, with a message naming no envelope. Every other
envelope stayed exactly as the assign left it.

The unit of atomicity for these is the budget move, not the batch, which is
what `undo_move` has always said; these tests hold the two to it.
"""

from datetime import date
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from igab.db.models import BudgetAssignment
from igab.services.card_payment import ensure_payment_category

from .factories import (
    add_budget_member,
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

MONTH = date(2026, 7, 1)


async def _assigned(db_session, budget_id) -> dict[str, D]:
    rows = (
        await db_session.execute(
            select(BudgetAssignment.category_id, BudgetAssignment.assigned).where(
                BudgetAssignment.budget_id == budget_id
            )
        )
    ).all()
    return {str(cat): amount for cat, amount in rows}


async def _budget(db_session, api_client):
    """Six funded envelopes, one card, one envelope overspent in cash.

    Enough envelopes that "the batch" and "one envelope" are visibly
    different things — the whole point of the report.
    """
    services = make_services(db_session)
    budget = await create_budget(db_session, await create_user(db_session))
    await add_budget_member(db_session, budget, api_client.test_user, role="owner")
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    card = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    await ensure_payment_category(db_session, card)
    await create_transaction(db_session, budget, checking, "3000.00", MONTH, category=inflow)

    cats: dict[str, object] = {}
    for i, name in enumerate(("Groceries", "Dining", "Fuel", "Fun", "Pets", "Gifts")):
        cat = await create_category(db_session, budget, everyday, name)
        cats[name] = cat
        await services.budgets.set_assignment(budget.id, cat.id, MONTH, D(str(50 + i * 25)))
    # Groceries ends the month 40 short, so Cover Overspending has work to do.
    await create_transaction(
        db_session, budget, checking, "-90.00", date(2026, 7, 8), category=cats["Groceries"]
    )
    await db_session.commit()
    return budget, cats


async def _apply(api_client, budget, strategy: str) -> str:
    r = await api_client.post(
        f"/api/v1/{budget.id}/assign/apply",
        json={"month": MONTH.isoformat(), "strategy": strategy},
    )
    assert r.status_code == 200, r.text
    batch_id = r.json()["batch_id"]
    assert batch_id, r.text
    return batch_id


async def _latest_batch_id(api_client, budget) -> str:
    """The batch the newest recorded change belongs to — what the toast holds
    onto for its Undo button."""
    r = await api_client.get(f"/api/v1/{budget.id}/changes", params={"limit": 1})
    assert r.status_code == 200, r.text
    return r.json()["changes"][0]["batch_id"]


async def _edit(api_client, budget, category_id, amount: str):
    """What a user does on seeing a bulk assign land wrong: fix one cell."""
    r = await api_client.patch(
        f"/api/v1/categories/{category_id}/assignment",
        json={"amount": float(amount)},
        params={"month": MONTH.isoformat(), "budget_id": str(budget.id)},
    )
    assert r.status_code in (200, 204), r.text


class TestBulkAssignUndo:
    async def test_undo_puts_every_envelope_back(self, db_session, api_client):
        budget, _ = await _budget(db_session, api_client)
        before = await _assigned(db_session, budget.id)
        batch_id = await _apply(api_client, budget, "reset_assigned")

        r = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")

        assert r.status_code == 200, r.text
        assert r.json()["skipped_change_ids"] == []
        assert await _assigned(db_session, budget.id) == before

    async def test_one_hand_edited_envelope_no_longer_vetoes_the_rest(self, db_session, api_client):
        """The reported bug, exactly: edit one cell, then undo.

        Before the fix this raised 409 and reverted nothing at all.
        """
        budget, cats = await _budget(db_session, api_client)
        before = await _assigned(db_session, budget.id)
        batch_id = await _apply(api_client, budget, "reset_assigned")
        await _edit(api_client, budget, cats["Fuel"].id, "999")

        r = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")

        assert r.status_code == 200, r.text
        after = await _assigned(db_session, budget.id)
        # The five untouched envelopes are back where they started...
        for name, cat in cats.items():
            if name != "Fuel":
                assert after[str(cat.id)] == before[str(cat.id)], name
        # ...and the one the user retyped keeps the figure they typed. Neither
        # 100 (the snapshot) nor 1099 (the delta) is what they asked for.
        assert after[str(cats["Fuel"].id)] == D("999")
        assert len(r.json()["skipped_change_ids"]) == 1

    async def test_the_skip_is_reported_rather_than_passed_off_as_a_clean_undo(
        self, db_session, api_client
    ):
        budget, cats = await _budget(db_session, api_client)
        batch_id = await _apply(api_client, budget, "reset_assigned")
        await _edit(api_client, budget, cats["Fun"].id, "500")
        await _edit(api_client, budget, cats["Pets"].id, "600")

        r = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")

        body = r.json()
        assert len(body["skipped_change_ids"]) == 2
        assert set(body["skipped_change_ids"]).isdisjoint(body["undone_change_ids"])

    async def test_refuses_when_every_envelope_has_moved_on(self, db_session, api_client):
        """Nothing to take back is still a refusal — with a message that says
        why, rather than the old "the item has been edited"."""
        budget, cats = await _budget(db_session, api_client)
        batch_id = await _apply(api_client, budget, "reset_assigned")
        for cat in cats.values():
            await _edit(api_client, budget, cat.id, "42")

        r = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")

        assert r.status_code == 409
        assert "assigned since" in r.json()["detail"]["message"]

    async def test_force_still_restores_the_snapshot_wholesale(self, db_session, api_client):
        """`force` is unchanged: it overrides the staleness check on every row,
        edited envelopes included, which is the whole point of asking for it."""
        budget, cats = await _budget(db_session, api_client)
        before = await _assigned(db_session, budget.id)
        batch_id = await _apply(api_client, budget, "reset_assigned")
        await _edit(api_client, budget, cats["Dining"].id, "999")

        r = await api_client.post(
            f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo", params={"force": True}
        )

        assert r.status_code == 200, r.text
        assert r.json()["skipped_change_ids"] == []
        assert await _assigned(db_session, budget.id) == before

    async def test_cmd_z_walks_back_the_edit_then_the_whole_assign(self, db_session, api_client):
        """⌘Z is strictly newest-first, so it never needs the skip: the hand
        edit goes back first, which leaves the envelope matching what the
        assign wrote, and the second ⌘Z then takes the batch cleanly.

        Worth pinning because it is the other half of the story — the skip
        exists for undoing the batch *by id* (the toast, the Activity page),
        where the user reaches past the edit rather than through it.
        """
        budget, cats = await _budget(db_session, api_client)
        before = await _assigned(db_session, budget.id)
        await _apply(api_client, budget, "reset_assigned")
        await _edit(api_client, budget, cats["Gifts"].id, "777")

        first = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert first.status_code == 200, first.text
        assert first.json()["skipped_change_ids"] == []

        second = await api_client.post(f"/api/v1/{budget.id}/changes/undo")
        assert second.status_code == 200, second.text
        assert second.json()["skipped_change_ids"] == []
        assert await _assigned(db_session, budget.id) == before

    async def test_cover_overspending_undoes_the_same_way(self, db_session, api_client):
        budget, cats = await _budget(db_session, api_client)
        before = await _assigned(db_session, budget.id)
        preview = await api_client.get(
            f"/api/v1/{budget.id}/cover-overspent/preview", params={"month": MONTH.isoformat()}
        )
        items = preview.json()["items"]
        assert items, "Groceries should be 40 short"
        apply = await api_client.post(
            f"/api/v1/{budget.id}/cover-overspent/apply",
            json={
                "month": MONTH.isoformat(),
                "items": [
                    {"category_id": i["category_id"], "proposed_addition": i["proposed_addition"]}
                    for i in items
                ],
            },
        )
        batch_id = apply.json()["batch_id"]

        r = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")

        assert r.status_code == 200, r.text
        assert await _assigned(db_session, budget.id) == before


class TestBatchesThatStayAllOrNothing:
    """The relaxation is named and narrow: budget moves only."""

    async def test_a_single_move_still_reports_the_plain_conflict(self, db_session, api_client):
        """One move is not a batch worth partitioning, so the ordinary message
        — which names the field that changed — is the honest answer."""
        budget, cats = await _budget(db_session, api_client)
        move = await api_client.post(
            f"/api/v1/{budget.id}/budget/move-money",
            json={
                "from_category_id": str(cats["Fun"].id),
                "to_category_id": str(cats["Pets"].id),
                "amount": 25,
                "month": MONTH.isoformat(),
            },
        )
        assert move.status_code in (200, 201, 204), move.text
        batch_id = await _latest_batch_id(api_client, budget)
        await _edit(api_client, budget, cats["Pets"].id, "999")

        r = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")

        assert r.status_code == 409
        assert r.json()["detail"]["fields"] == ["assigned"]

    @pytest.mark.parametrize("strategy", ["reset_assigned", "reset_available"])
    async def test_money_is_conserved_whatever_is_skipped(self, db_session, api_client, strategy):
        """A skipped envelope keeps its own figure and nothing else shifts:
        assignments are the only thing undo writes, so the budget stays
        internally consistent however the skips fall."""
        budget, cats = await _budget(db_session, api_client)
        before = await _assigned(db_session, budget.id)
        batch_id = await _apply(api_client, budget, strategy)
        applied = await _assigned(db_session, budget.id)
        if applied == before:
            pytest.skip("strategy moved nothing on this shape")
        await _edit(api_client, budget, cats["Fuel"].id, "123")

        r = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")
        assert r.status_code == 200, r.text

        after = await _assigned(db_session, budget.id)
        expected = dict(before) | {str(cats["Fuel"].id): D("123")}
        assert after == expected
