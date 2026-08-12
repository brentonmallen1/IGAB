"""Plan vs Reality report: assigned vs spent per category per month.

The report deliberately ignores envelope carryover — it measures monthly plan
discipline. A category coasting on January's surplus is still over-plan in
February if nothing was assigned in February.
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
TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)


def _months_back(n: int) -> date:
    month = THIS_MONTH.month - n
    year = THIS_MONTH.year
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


async def _fetch(api_client, budget_id, **params):
    resp = await api_client.get(f"/api/v1/{budget_id}/reports/plan-vs-reality", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _cat(body, category_id):
    return next(c for c in body["categories"] if c["category_id"] == str(category_id))


def _cell(cat, month: date):
    return next(m for m in cat["monthly"] if m["month"] == month.isoformat())


async def test_monthly_matrix_and_totals(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")

    m1, m0 = _months_back(1), THIS_MONTH
    await create_budget_assignment(db_session, budget, groceries, m1, "200.00")
    await create_transaction(
        db_session, budget, account, "-150.00", m1.replace(day=10), category=groceries
    )
    await create_budget_assignment(db_session, budget, groceries, m0, "100.00")
    await create_transaction(db_session, budget, account, "-130.00", m0, category=groceries)

    body = await _fetch(api_client, budget.id, months=6)
    assert len(body["months"]) == 6
    assert body["months"][-1] == m0.isoformat()

    cat = _cat(body, groceries.id)
    prev = _cell(cat, m1)
    assert D(prev["assigned"]) == D("200.00")
    assert D(prev["spent"]) == D("150.00")
    assert D(prev["variance"]) == D("50.00")
    cur = _cell(cat, m0)
    assert D(cur["variance"]) == D("-30.00")
    # Empty months are zero-filled so the frontend gets a full grid
    empty = _cell(cat, _months_back(4))
    assert (D(empty["assigned"]), D(empty["spent"])) == (D("0"), D("0"))

    assert cat["months_active"] == 2
    assert cat["months_over"] == 1
    assert D(cat["total_assigned"]) == D("300.00")
    assert D(cat["total_spent"]) == D("280.00")
    assert D(body["total_assigned"]) == D("300.00")
    assert D(body["total_spent"]) == D("280.00")


async def test_carryover_is_ignored_by_design(api_client, db_session):
    """Assigned once, spent for three months: months without an assignment
    are over-plan even though the envelope still had money."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Slush")

    await create_budget_assignment(db_session, budget, cat, _months_back(2), "300.00")
    for n in (2, 1, 0):
        await create_transaction(
            db_session, budget, account, "-50.00", _months_back(n), category=cat
        )

    body = await _fetch(api_client, budget.id, months=6)
    entry = _cat(body, cat.id)
    assert entry["months_over"] == 2  # the two months with spending but no assignment
    assert D(_cell(entry, _months_back(2))["variance"]) == D("250.00")
    assert D(_cell(entry, _months_back(1))["variance"]) == D("-50.00")


async def test_chronic_flag_threshold(api_client, db_session):
    """Over in 3 of the last 6 months → chronic; 2 of 6 → not."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    chronic_cat = await create_category(db_session, budget, group, "Dining")
    occasional = await create_category(db_session, budget, group, "Hobbies")

    for n in (0, 1, 2):
        await create_transaction(
            db_session, budget, account, "-40.00", _months_back(n), category=chronic_cat
        )
    for n in (0, 1):
        await create_transaction(
            db_session, budget, account, "-40.00", _months_back(n), category=occasional
        )

    body = await _fetch(api_client, budget.id, months=12)
    assert _cat(body, chronic_cat.id)["chronic"] is True
    assert _cat(body, occasional.id)["chronic"] is False
    assert body["chronic_count"] == 1
    # Chronic categories sort first
    assert body["categories"][0]["category_id"] == str(chronic_cat.id)
    assert D(_cat(body, chronic_cat.id)["avg_overspend"]) == D("40.00")


async def test_old_overruns_are_not_chronic(api_client, db_session):
    """Three overruns 7+ months ago don't make a category chronic now."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Reformed")

    for n in (7, 8, 9):
        await create_transaction(
            db_session, budget, account, "-40.00", _months_back(n), category=cat
        )

    body = await _fetch(api_client, budget.id, months=12)
    entry = _cat(body, cat.id)
    assert entry["months_over"] == 3
    assert entry["chronic"] is False


async def test_excludes_system_and_uncategorized(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    groceries = await create_category(db_session, budget, group, "Groceries")
    income_cat = await create_category(db_session, budget, income_group, "Ready to Assign")

    await create_transaction(db_session, budget, account, "-60.00", THIS_MONTH, category=groceries)
    await create_transaction(db_session, budget, account, "3000.00", THIS_MONTH, category=income_cat)
    await create_transaction(db_session, budget, account, "-45.00", THIS_MONTH)  # uncategorized
    await create_transaction(
        db_session, budget, account, "-99.00", THIS_MONTH, category=groceries, is_deleted=True
    )

    body = await _fetch(api_client, budget.id, months=6)
    assert [c["category_id"] for c in body["categories"]] == [str(groceries.id)]
    assert D(body["total_spent"]) == D("60.00")


async def test_months_window_bounds(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")
    await create_transaction(
        db_session, budget, account, "-10.00", _months_back(8), category=cat
    )

    body = await _fetch(api_client, budget.id, months=6)
    assert body["categories"] == []  # activity is outside the 6-month window
    body = await _fetch(api_client, budget.id, months=12)
    assert len(_cat(body, cat.id)["monthly"]) == 12

    resp = await api_client.get(
        f"/api/v1/{budget.id}/reports/plan-vs-reality", params={"months": 48}
    )
    assert resp.status_code == 422
