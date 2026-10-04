"""Read-only months before the import month, as YNAB displayed them.

A fresh import keeps every Plan.csv row (`db.models.ImportPlanMonth`); the
Budget page shows a month before the import month from those rows, read-only,
and never re-derives it. The parity fixture's plan runs June–August 2026 and
B = August, so June and July are the history. Figures are the fixture's own.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Category, ImportAnchor, ImportPlanMonth

from .anchored_budget import build_anchored_budget
from .ynab_agreement import fixture_zip

JUN, JUL, AUG = date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)
D = Decimal


async def _imported(api_client, tmp_path, mode="anchored"):
    resp = await api_client.post(
        "/api/v1/budgets/import-ynab",
        files={"file": ("export.zip", fixture_zip(tmp_path).read_bytes(), "application/zip")},
        data={"name": f"History {mode}", "history_mode": mode},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["budget"]["id"]


async def _category(db_session, budget_id, name):
    return (
        await db_session.execute(
            select(Category).where(Category.budget_id == budget_id, Category.name == name)
        )
    ).scalar_one()


async def test_the_import_keeps_every_plan_month_as_exported(db_session, tmp_path):
    """Every row of every month, in YNAB's order, under YNAB's names — and
    the anchor month's Available is the anchor's own figure. Imported with the
    Visa typed as a card, so its "Credit Card Payments" row has an envelope."""
    from .ynab_agreement import import_export

    types = {
        "Checking": ("checking", True),
        "Savings": ("savings", True),
        "Visa": ("credit_card", True),
        "Brokerage": ("investment", False),
    }
    _, budget_id, _ = await import_export(db_session, fixture_zip(tmp_path), account_types=types)
    rows = (
        (
            await db_session.execute(
                select(ImportPlanMonth)
                .where(ImportPlanMonth.budget_id == budget_id)
                .order_by(ImportPlanMonth.month, ImportPlanMonth.position)
            )
        )
        .scalars()
        .all()
    )
    assert {r.month for r in rows} == {JUN, JUL, AUG}
    june = [r for r in rows if r.month == JUN]
    assert [r.category for r in june[:3]] == ["Rent", "Utilities", "Groceries"]
    groceries = next(r for r in june if r.category == "Groceries")
    assert (groceries.assigned, groceries.activity, groceries.available) == (
        D("300"),
        D("-350"),
        D("-50"),
    )
    # The Visa's "Credit Card Payments" row resolves to the card's envelope.
    visa_row = next(r for r in june if r.category_group == "Credit Card Payments")
    assert visa_row.category_id is not None

    # July is B−1: what the anchor seeded is what the plan said.
    utilities = await _category(db_session, budget_id, "Utilities")
    anchor = (
        await db_session.execute(
            select(ImportAnchor.amount).where(
                ImportAnchor.budget_id == budget_id, ImportAnchor.category_id == utilities.id
            )
        )
    ).scalar_one()
    july_utilities = next(r for r in rows if r.month == JUL and r.category == "Utilities")
    assert july_utilities.available == anchor == D("-50")


async def test_a_month_before_the_import_is_served_read_only(db_session, api_client, tmp_path):
    budget_id = await _imported(api_client, tmp_path)
    july = (await api_client.get(f"/api/v1/{budget_id}/months/{JUL.isoformat()}")).json()
    assert july["read_only"] is True
    assert july["history_starts"] == JUN.isoformat()
    august = (await api_client.get(f"/api/v1/{budget_id}/months/{AUG.isoformat()}")).json()
    assert august["read_only"] is False
    assert august["history_starts"] == JUN.isoformat()


async def test_the_history_month_shows_ynabs_figures(db_session, api_client, tmp_path):
    """July as YNAB had it: Utilities given 100, spent 150, ended 50 short.
    No income rows — they hold no money."""
    budget_id = await _imported(api_client, tmp_path)
    resp = await api_client.get(f"/api/v1/{budget_id}/months/{JUL.isoformat()}/history")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["import_month"], body["history_starts"]) == (AUG.isoformat(), JUN.isoformat())
    utilities = next(r for r in body["rows"] if r["category"] == "Utilities")
    assert (D(utilities["assigned"]), D(utilities["activity"]), D(utilities["available"])) == (
        D("100"),
        D("-150"),
        D("-50"),
    )
    assert all(r["category_group"] != "Inflow" for r in body["rows"])


async def test_there_is_no_history_from_the_import_month_on(db_session, api_client, tmp_path):
    budget_id = await _imported(api_client, tmp_path)
    resp = await api_client.get(f"/api/v1/{budget_id}/months/{AUG.isoformat()}/history")
    assert resp.status_code == 404


async def test_a_rederived_budget_has_live_months_instead(db_session, api_client, tmp_path):
    """Working out every month means every month is IGAB's and editable — the
    stored figures stay, unread, for switching back."""
    budget_id = await _imported(api_client, tmp_path, mode="rederived")
    july = (await api_client.get(f"/api/v1/{budget_id}/months/{JUL.isoformat()}")).json()
    assert (july["read_only"], july["history_starts"], july["anchor_month"]) == (False, None, None)
    history = await api_client.get(f"/api/v1/{budget_id}/months/{JUL.isoformat()}/history")
    assert history.status_code == 404


async def test_a_read_only_month_refuses_a_plan_write(db_session, api_client, tmp_path):
    """The server decides, not just the screen: assigning or moving money in
    July of an anchored budget is refused, and allowed once it re-derives."""
    budget_id = await _imported(api_client, tmp_path)
    groceries = await _category(db_session, budget_id, "Groceries")
    refused = await api_client.patch(
        f"/api/v1/categories/{groceries.id}/assignment",
        params={"month": JUL.isoformat(), "budget_id": budget_id},
        json={"amount": "25.00"},
    )
    assert refused.status_code == 400, refused.text
    assert "YNAB's own figures" in refused.json()["detail"]
    moved = await api_client.post(
        f"/api/v1/{budget_id}/budget/move-money",
        json={
            "from_category_id": None,
            "to_category_id": str(groceries.id),
            "amount": "10.00",
            "month": JUL.isoformat(),
        },
    )
    assert moved.status_code == 400, moved.text

    await api_client.put(f"/api/v1/budgets/{budget_id}/history", json={"mode": "rederived"})
    allowed = await api_client.patch(
        f"/api/v1/categories/{groceries.id}/assignment",
        params={"month": JUL.isoformat(), "budget_id": budget_id},
        json={"amount": "25.00"},
    )
    assert allowed.status_code == 204, allowed.text


async def test_undo_can_still_put_back_an_earlier_month(db_session, api_client):
    """An assignment made while re-derived, then the budget switched back:
    undoing it restores what was there, which is not a new plan — the guard
    is on writes, not on the change log."""
    b = await build_anchored_budget(db_session, api_client.test_user)
    await api_client.put(f"/api/v1/budgets/{b.budget.id}/history", json={"mode": "rederived"})
    resp = await api_client.patch(
        f"/api/v1/categories/{b.groceries.id}/assignment",
        params={"month": JUN.isoformat(), "budget_id": str(b.budget.id)},
        json={"amount": "25.00"},
    )
    assert resp.status_code == 204, resp.text
    # Undo the assignment first (the switch back would be the latest change).
    undone = await api_client.post(f"/api/v1/{b.budget.id}/changes/undo")
    assert undone.status_code == 200, undone.text


async def test_category_history_reads_ynabs_available_before_the_import(
    db_session, api_client, tmp_path
):
    """The envelope series behind Category History agrees with the read-only
    grid: June's Groceries is YNAB's −50, not a figure walked back from the
    anchor."""
    from igab.guide.detection import budget_service_from

    budget_id = await _imported(api_client, tmp_path)
    groceries = await _category(db_session, budget_id, "Groceries")
    series = await budget_service_from(db_session).envelope_series(
        budget_id, [groceries.id], [JUN, JUL]
    )
    assert series[groceries.id].available[0] == D("-50")
    assert series[groceries.id].unrecovered_through is None


async def test_an_older_import_keeps_todays_clamp(db_session, api_client):
    """An import from before the figures were kept has an anchor and no plan
    months: earlier months stay read-only on the server, and with no history
    to show the client keeps stopping at the import month."""
    b = await build_anchored_budget(db_session, api_client.test_user)
    june = (await api_client.get(f"/api/v1/{b.budget.id}/months/{JUN.isoformat()}")).json()
    assert (june["read_only"], june["history_starts"]) == (True, None)
    history = await api_client.get(f"/api/v1/{b.budget.id}/months/{JUN.isoformat()}/history")
    assert history.status_code == 404
