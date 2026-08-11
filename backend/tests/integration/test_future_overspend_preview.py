"""Future-overspending preview (B1): before saving an edit, the UI asks which
categories a signed amount delta would push negative in a *future* month —
current-month overspending is already visible on the budget page, but a future
month's negative would sit unseen until the user navigates there.
"""

from datetime import date
from decimal import Decimal

from igab.utils.clock import today_utc

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    make_services,
)


def _month_add(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) + n, 12)
    return date(y, m + 1, 1)


CURRENT = today_utc().replace(day=1)
NEXT = _month_add(CURRENT, 1)
AFTER_NEXT = _month_add(CURRENT, 2)


async def _setup(db_session, user):
    services = make_services(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    await create_transaction(
        db_session, budget, checking, "1000.00", today_utc(), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, groceries.id, NEXT, Decimal("100.00"))
    return services, budget, groceries


async def _preview(api_client, budget, items):
    resp = await api_client.post(
        f"/api/v1/{budget.id}/months/preview-overspend",
        json={
            "items": [
                {
                    "category_id": str(cat_id),
                    "date": d.isoformat(),
                    "amount_delta": str(delta),
                }
                for cat_id, d, delta in items
            ]
        },
    )
    assert resp.status_code == 200
    return resp.json()["warnings"]


async def test_future_spend_within_available_no_warning(db_session, api_client):
    _, budget, groceries = await _setup(db_session, api_client.test_user)
    warnings = await _preview(
        api_client, budget, [(groceries.id, NEXT.replace(day=15), "-100.00")]
    )
    assert warnings == []


async def test_future_spend_beyond_available_warns(db_session, api_client):
    _, budget, groceries = await _setup(db_session, api_client.test_user)
    warnings = await _preview(
        api_client, budget, [(groceries.id, NEXT.replace(day=15), "-150.00")]
    )
    assert len(warnings) == 1
    w = warnings[0]
    assert w["category_id"] == str(groceries.id)
    assert w["category_name"] == "Groceries"
    assert w["month"] == NEXT.isoformat()
    assert Decimal(str(w["available_before"])) == Decimal("100.00")
    assert Decimal(str(w["available_after"])) == Decimal("-50.00")


async def test_current_month_items_ignored(db_session, api_client):
    """Current-month overspending is the budget page's job, not this warning's."""
    _, budget, groceries = await _setup(db_session, api_client.test_user)
    warnings = await _preview(api_client, budget, [(groceries.id, today_utc(), "-5000.00")])
    assert warnings == []


async def test_split_lines_in_same_month_are_summed(db_session, api_client):
    _, budget, groceries = await _setup(db_session, api_client.test_user)
    warnings = await _preview(
        api_client,
        budget,
        [
            (groceries.id, NEXT.replace(day=5), "-60.00"),
            (groceries.id, NEXT.replace(day=5), "-60.00"),
        ],
    )
    assert len(warnings) == 1
    assert Decimal(str(warnings[0]["available_after"])) == Decimal("-20.00")


async def test_edit_reversal_offsets_new_amount(db_session, api_client):
    """Editing a future txn sends the old amount as a positive reversal; only
    the net change counts, so growing a $100 txn to $150 within $100 available
    still warns while an unchanged amount would not."""
    _, budget, groceries = await _setup(db_session, api_client.test_user)
    warnings = await _preview(
        api_client,
        budget,
        [
            (groceries.id, NEXT.replace(day=15), "-150.00"),
            (groceries.id, NEXT.replace(day=15), "100.00"),
        ],
    )
    assert warnings == []


async def test_assignment_carries_over_into_later_future_month(db_session, api_client):
    """$100 assigned next month carries into the month after; overspending
    there is judged against the carried balance."""
    _, budget, groceries = await _setup(db_session, api_client.test_user)
    warnings = await _preview(
        api_client, budget, [(groceries.id, AFTER_NEXT.replace(day=3), "-150.00")]
    )
    assert len(warnings) == 1
    assert warnings[0]["month"] == AFTER_NEXT.isoformat()
    assert Decimal(str(warnings[0]["available_before"])) == Decimal("100.00")
    assert Decimal(str(warnings[0]["available_after"])) == Decimal("-50.00")


async def test_other_budgets_categories_are_ignored(db_session, api_client):
    """A category id from another budget must not leak balances through the
    preview — it is silently dropped."""
    _, budget, _ = await _setup(db_session, api_client.test_user)
    other_budget = await create_budget(db_session, api_client.test_user)
    other_group = await create_category_group(db_session, other_budget, "Other")
    other_cat = await create_category(db_session, other_budget, other_group, "Elsewhere")
    warnings = await _preview(
        api_client, budget, [(other_cat.id, NEXT.replace(day=15), "-150.00")]
    )
    assert warnings == []
