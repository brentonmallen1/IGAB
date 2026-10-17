"""The target editor's suggestions, served (`services/target_suggestions.py`).

Average and peak spending come from the plan ledger over the last twelve
complete months, as the Category History report states them; the peak balance
is the Budget page's month-end Available. The running month is never read.
Amounts are invented and round.
"""

from datetime import date
from decimal import Decimal

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
)

D = Decimal
TODAY = date(2026, 8, 15)
MAY, JUNE, JULY, AUGUST = (date(2026, m, 3) for m in (5, 6, 7, 8))


async def _world(db_session, user):
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    return budget, checking, group


async def _suggest(api_client, budget, category, today=TODAY):
    resp = await api_client.get(
        f"/api/v1/{budget.id}/categories/{category.id}/target-suggestions",
        params={"client_today": today.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in ("average_spent", "peak_spent", "peak_available"):
        body[key] = None if body[key] is None else D(str(body[key]))
    return body


async def test_no_history_suggests_nothing(db_session, api_client):
    budget, _, group = await _world(db_session, api_client.test_user)
    bare = await create_category(db_session, budget, group, "Bare")

    body = await _suggest(api_client, budget, bare)

    assert body["average_spent"] == D("0")
    assert body["peak_spent"] is None and body["peak_spent_month"] is None
    assert body["peak_available"] is None and body["peak_available_month"] is None


async def test_a_young_budget_counts_only_the_months_it_has(db_session, api_client):
    """History starts in May, so three complete months by mid-August: 100,
    300 and 200 spent — 200 a month on average, 300 at the peak in June.
    Assigned 400 in May and 500 in July, so it ended May and July holding
    300 each; the later month is named."""
    budget, checking, group = await _world(db_session, api_client.test_user)
    groceries = await create_category(db_session, budget, group, "Groceries")
    for amount, day in (("-100", MAY), ("-300", JUNE), ("-200", JULY)):
        await create_transaction(db_session, budget, checking, amount, day, category=groceries)
    await create_budget_assignment(db_session, budget, groceries, date(2026, 5, 1), "400")
    await create_budget_assignment(db_session, budget, groceries, date(2026, 7, 1), "500")
    # The running month is month-to-date: never a peak, never averaged.
    await create_transaction(db_session, budget, checking, "-999", AUGUST, category=groceries)
    await create_budget_assignment(db_session, budget, groceries, date(2026, 8, 1), "5000")

    body = await _suggest(api_client, budget, groceries)

    assert body["months_counted"] == 3
    assert body["average_spent"] == D("200.00")
    assert (body["peak_spent"], body["peak_spent_month"]) == (D("300"), "2026-06-01")
    assert (body["peak_available"], body["peak_available_month"]) == (D("300"), "2026-07-01")


async def test_refunds_net_the_spending_and_never_suggest_below_zero(db_session, api_client):
    """May spent 100; June's 150 refund beat its spending. Net, the window
    spent less than nothing: no monthly amount is suggested, and the peak
    month is still May's 100."""
    budget, checking, group = await _world(db_session, api_client.test_user)
    shopping = await create_category(db_session, budget, group, "Shopping")
    await create_transaction(db_session, budget, checking, "-100", MAY, category=shopping)
    await create_transaction(db_session, budget, checking, "150", JUNE, category=shopping)

    body = await _suggest(api_client, budget, shopping)

    assert body["average_spent"] == D("0")
    assert (body["peak_spent"], body["peak_spent_month"]) == (D("100"), "2026-05-01")


async def test_the_average_is_the_category_history_reports(db_session, api_client):
    """One figure, two places: the suggestion chip and the report the
    inspector draws read the same average over the same twelve months."""
    budget, checking, group = await _world(db_session, api_client.test_user)
    dining = await create_category(db_session, budget, group, "Dining")
    for amount, day in (("-90", MAY), ("-60", JUNE), ("-45", JULY)):
        await create_transaction(db_session, budget, checking, amount, day, category=dining)

    body = await _suggest(api_client, budget, dining)
    report = (
        await api_client.get(
            f"/api/v1/{budget.id}/reports/category-history",
            params={"category_id": str(dining.id), "client_today": TODAY.isoformat()},
        )
    ).json()

    assert body["average_spent"] == D(str(report["average_spent"])) == D("65.00")
    assert body["months_counted"] == report["months_averaged"] == 3


async def test_another_budgets_category_is_refused(db_session, api_client):
    budget, _, _ = await _world(db_session, api_client.test_user)
    other, _, other_group = await _world(db_session, api_client.test_user)
    foreign = await create_category(db_session, other, other_group, "Foreign")

    resp = await api_client.get(
        f"/api/v1/{budget.id}/categories/{foreign.id}/target-suggestions",
        params={"client_today": TODAY.isoformat()},
    )
    # `require_in_budget`, as the history endpoints beside it answer.
    assert resp.status_code == 400, resp.text
    assert "does not belong" in resp.json()["detail"]
