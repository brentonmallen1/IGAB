"""Plan vs Spent: each category's plan against its spending per month, with a
total per month and per category.

The report deliberately ignores envelope carryover — it measures monthly plan
discipline. A category coasting on January's surplus is still over-plan in
February if nothing was assigned in February.

"N months" is N complete months and the running month beside them (D5,
`domain.dates.ReportWindow`): the running month's cells are drawn, and no
verdict or total counts them. The window starts no earlier than the budget's
first transaction, so tests that need the whole window anchor the history with
an uncategorized row, which the plan never counts.
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
    resp = await api_client.get(f"/api/v1/{budget_id}/reports/plan-vs-spent", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _cat(body, category_id):
    return next(c for c in body["categories"] if c["category_id"] == str(category_id))


def _cell(cat, month: date):
    return next(m for m in cat["monthly"] if m["month"] == month.isoformat())


async def _history_from(db_session, budget, account, months_back: int) -> None:
    """Start the budget's history `months_back` months ago with a row the plan
    never counts (uncategorized), so the window is not clamped short."""
    await create_transaction(db_session, budget, account, "-1.00", _months_back(months_back))


async def test_monthly_matrix_and_totals(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")

    await _history_from(db_session, budget, account, 6)
    m1, m0 = _months_back(1), THIS_MONTH
    await create_budget_assignment(db_session, budget, groceries, m1, "200.00")
    await create_transaction(
        db_session, budget, account, "-150.00", m1.replace(day=10), category=groceries
    )
    await create_budget_assignment(db_session, budget, groceries, m0, "100.00")
    await create_transaction(db_session, budget, account, "-130.00", m0, category=groceries)

    body = await _fetch(api_client, budget.id, months=6)
    # Six complete months, then the running one.
    assert len(body["months"]) == 7
    assert body["months"][-1] == body["running_month"] == m0.isoformat()

    cat = _cat(body, groceries.id)
    prev = _cell(cat, m1)
    assert D(prev["assigned"]) == D("200.00")
    assert D(prev["spent"]) == D("150.00")
    assert D(prev["variance"]) == D("50.00")
    # The running month's cell is drawn, month-to-date...
    cur = _cell(cat, m0)
    assert D(cur["variance"]) == D("-30.00")
    # Empty months are zero-filled so the frontend gets a full grid
    empty = _cell(cat, _months_back(4))
    assert (D(empty["assigned"]), D(empty["spent"])) == (D("0"), D("0"))

    # ...and counted in no verdict or total: those are the complete months'.
    assert cat["months_active"] == 1
    assert cat["months_over"] == 0
    assert D(cat["total"]["assigned"]) == D("200.00")
    assert D(cat["total"]["spent"]) == D("150.00")
    assert D(body["total_assigned"]) == D("200.00")
    assert D(body["total_spent"]) == D("150.00")
    # The totals row: last month is its one cell, the running month is drawn
    # with no running total.
    by_month = {t["month"]: t for t in body["month_totals"]}
    assert D(by_month[m1.isoformat()]["variance"]) == D("50.00")
    assert D(by_month[m1.isoformat()]["cumulative_variance"]) == D("50.00")
    assert by_month[m0.isoformat()]["partial_month"] is True
    assert by_month[m0.isoformat()]["cumulative_variance"] is None
    assert D(by_month[m0.isoformat()]["spent"]) == D("130.00")


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
    # Last month spent with no assignment; this month did too, but it is
    # still running and is no verdict yet.
    assert entry["months_over"] == 1
    assert D(_cell(entry, _months_back(0))["variance"]) == D("-50.00")
    assert D(_cell(entry, _months_back(2))["variance"]) == D("250.00")
    assert D(_cell(entry, _months_back(1))["variance"]) == D("-50.00")


async def test_chronic_flag_threshold(api_client, db_session):
    """Over in 3 of the last 6 complete months → chronic; 2 of 6 → not, and
    the running month is not a third: it is not over yet."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    chronic_cat = await create_category(db_session, budget, group, "Dining")
    occasional = await create_category(db_session, budget, group, "Hobbies")

    for n in (1, 2, 3):
        await create_transaction(
            db_session, budget, account, "-40.00", _months_back(n), category=chronic_cat
        )
    for n in (0, 1, 2):
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

    last = _months_back(1)
    await create_transaction(db_session, budget, account, "-60.00", last, category=groceries)
    await create_transaction(db_session, budget, account, "3000.00", last, category=income_cat)
    await create_transaction(db_session, budget, account, "-45.00", last)  # uncategorized
    await create_transaction(
        db_session, budget, account, "-99.00", last, category=groceries, is_deleted=True
    )

    body = await _fetch(api_client, budget.id, months=6)
    assert [c["category_id"] for c in body["categories"]] == [str(groceries.id)]
    assert D(body["total_spent"]) == D("60.00")


async def test_months_window_bounds(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    cat = await create_category(db_session, budget, group, "Groceries")
    await _history_from(db_session, budget, account, 14)
    await create_transaction(db_session, budget, account, "-10.00", _months_back(8), category=cat)

    body = await _fetch(api_client, budget.id, months=6)
    assert body["categories"] == []  # activity is outside the 6-month window
    body = await _fetch(api_client, budget.id, months=12)
    # Twelve complete months and the running one.
    assert len(_cat(body, cat.id)["monthly"]) == 13

    # 48 months used to be a 422 here and nowhere else: this report carried a
    # 24-month ceiling of its own while seven siblings had none. The ceiling is
    # now the one shared MAX_REPORT_MONTHS, so a four-year window is answered.
    resp = await api_client.get(f"/api/v1/{budget.id}/reports/plan-vs-spent", params={"months": 48})
    assert resp.status_code == 200, resp.text

    # The 3-month FLOOR is this report's own rule and stays: "chronic" means
    # over-plan in 3+ of the window's last 6 months, which a shorter window
    # cannot say. So does the shared ceiling.
    assert (
        await api_client.get(f"/api/v1/{budget.id}/reports/plan-vs-spent", params={"months": 2})
    ).status_code == 422
    assert (
        await api_client.get(f"/api/v1/{budget.id}/reports/plan-vs-spent", params={"months": 601})
    ).status_code == 422


async def test_a_drained_envelope_is_not_a_chronic_overspender(db_session, api_client):
    """`spent > assigned` read a NEGATIVE assignment as overspending.

    A negative assignment is money moved back OUT of an envelope — a plan being
    reduced, not a household overspending. Drain 300 from an envelope that
    spent nothing and `0 > -300` flagged the month; do it in three of the last
    six and the report named that envelope the household's worst habit, with no
    spending in it at all.

    The plan floors at zero, and the cell's `variance` uses the same floored
    plan, because the matrix tints a negative variance red — a drained envelope
    was being coloured as overspent while the chronic flag beside it disagreed.
    """
    budget = await create_budget(db_session, api_client.test_user)
    await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Goals")
    drained = await create_category(db_session, budget, group, "Car Repairs")

    for n in (0, 1, 2):
        await create_budget_assignment(db_session, budget, drained, _months_back(n), "-300.00")
    await db_session.commit()

    body = await _fetch(api_client, budget.id, months=6)

    assert body["chronic_count"] == 0
    # A row — something was assigned, if negatively (`PlanMonth.quiet`) — but
    # every cell on plan: no plan, nothing spent, never over. Before the floor
    # each cell was tinted as a 300 overspend.
    (row,) = [c for c in body["categories"] if c["category_id"] == str(drained.id)]
    assert row["months_over"] == 0
    assert not row["chronic"]
    drained_cells = [m for m in row["monthly"] if m["active"]]
    assert len(drained_cells) == 3
    assert all(
        (D(m["plan"]), D(m["variance"]), m["over"]) == (D("0"), D("0"), False)
        for m in drained_cells
    )


async def test_real_overspending_of_a_drained_envelope_still_counts(db_session, api_client):
    """The floor must not hide genuine overspending: with the plan at zero,
    money actually spent out of the envelope is over by the whole amount.
    """
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Goals")
    cat_obj = await create_category(db_session, budget, group, "Car Repairs")

    last = _months_back(1)
    await create_budget_assignment(db_session, budget, cat_obj, last, "-300.00")
    await create_transaction(
        db_session, budget, checking, "-120.00", last.replace(day=10), category=cat_obj
    )
    await db_session.commit()

    body = await _fetch(api_client, budget.id, months=6)
    cat = _cat(body, cat_obj.id)

    assert cat["months_over"] == 1
    # Over by 120 against a floored plan of 0 — not by 420 against -300.
    assert D(cat["avg_overspend"]) == D("120.00")
    assert D(_cell(cat, last)["variance"]) == D("-120.00")


class TestTheTotalColumnGivesTheCellsVerdict:
    """The Total column was Budget vs Actual, which answered the same question
    over a window and did not floor: it served `assigned - spent` raw, and its
    chart decided overspent for itself from `spent > assigned`. Over one
    drained envelope the two reports gave opposite verdicts — neutral on the
    matrix, a red 300 overrun beside it, and quoted to the AI as -300. Both
    serve `domain.plan.plan_outcome`, and now they are one response."""

    async def test_a_drained_envelope_is_on_plan_in_its_cell_and_its_total(
        self, db_session, api_client
    ):
        budget = await create_budget(db_session, api_client.test_user)
        await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Goals")
        drained = await create_category(db_session, budget, group, "Car Repairs")
        await create_budget_assignment(db_session, budget, drained, _months_back(1), "-300.00")
        await db_session.commit()

        body = await _fetch(api_client, budget.id, months=3)
        row = _cat(body, drained.id)
        total = row["total"]
        assert (D(total["plan"]), D(total["variance"]), total["over"]) == (D("0"), D("0"), False)
        cell = _cell(row, _months_back(1))
        assert (cell["active"], cell["over"], D(cell["variance"])) == (True, False, D("0"))
        assert D(body["total_variance"]) == D("0")

    async def test_real_spending_is_over_by_the_same_amount_in_both(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Goals")
        drained = await create_category(db_session, budget, group, "Car Repairs")
        last = _months_back(1)
        await create_budget_assignment(db_session, budget, drained, last, "-300.00")
        await create_transaction(
            db_session, budget, checking, "-120.00", last.replace(day=10), category=drained
        )
        await db_session.commit()

        body = await _fetch(api_client, budget.id, months=3)
        row = _cat(body, drained.id)
        total = row["total"]

        assert total["over"] is True
        # 120, not the 420 the unfloored subtraction ranked it by.
        assert D(total["variance"]) == D("-120.00")
        assert D(_cell(row, last)["variance"]) == D("-120.00")
        # And the headline says the same. It was raw assigned - spent, -420
        # here, above a row reading -120.
        assert D(body["total_variance"]) == D("-120.00")
        # No plan to take a share of: null, which the page prints "no plan".
        # It was 0.0, which printed as "0.0%" — on plan to the cent.
        assert total["variance_pct"] is None


class TestScope:
    """Budget vs Actual took the filter bar's categories, tags and saved
    filters; the one report keeps that, and the Guide reads it unscoped."""

    async def test_the_category_scope_narrows_every_figure(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        dining = await create_category(db_session, budget, group, "Dining")
        last = _months_back(1)
        for c, amount in ((groceries, "-80.00"), (dining, "-40.00")):
            await create_transaction(
                db_session, budget, checking, amount, last.replace(day=5), category=c
            )
        await db_session.commit()

        body = await _fetch(api_client, budget.id, months=3, category_ids=str(groceries.id))
        assert [c["category_id"] for c in body["categories"]] == [str(groceries.id)]
        assert D(body["total_spent"]) == D("80.00")
        by_month = {t["month"]: t for t in body["month_totals"]}
        assert D(by_month[last.isoformat()]["spent"]) == D("80.00")
        assert body["filter_unavailable"] is False

    async def test_a_missing_saved_filter_says_so(self, db_session, api_client):
        budget = await create_budget(db_session, api_client.test_user)
        body = await _fetch(
            api_client, budget.id, months=3, filter_id="00000000-0000-0000-0000-000000000000"
        )
        assert body["filter_unavailable"] is True


class TestTheAssistantReadsTheSameMonths:
    """The AI's `budget_vs_actual` is the Total column over dates it is asked
    for, widened to whole months: a plan is a month's, so half a month's
    spending against the month's whole assignment would read under plan."""

    async def test_a_range_that_cuts_months_reads_them_whole_and_agrees(
        self, db_session, api_client
    ):
        from igab.ai.tools import handlers
        from igab.ai.tools.context import build_tool_context
        from igab.domain.dates import month_end

        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Goals")
        gifts = await create_category(db_session, budget, group, "Gifts")
        await _history_from(db_session, budget, checking, 3)
        two, one = _months_back(2), _months_back(1)
        # 300 assigned, then swept back out the next month, and 80 spent late
        # in the second month — after the day the range names.
        await create_budget_assignment(db_session, budget, gifts, two, "300.00")
        await create_budget_assignment(db_session, budget, gifts, one, "-300.00")
        await create_transaction(
            db_session, budget, checking, "-80.00", one.replace(day=25), category=gifts
        )
        await db_session.commit()

        ctx = await build_tool_context(db_session, budget.id, TODAY)
        result = await handlers.budget_vs_actual(
            ctx,
            {
                "start_date": two.replace(day=15).isoformat(),
                "end_date": one.replace(day=10).isoformat(),
            },
        )
        assert (result["start_date"], result["end_date"]) == (
            two.isoformat(),
            month_end(one).isoformat(),
        )
        # Month by month: 300 under, then no plan and 80 spent — 220 under.
        (row,) = result["rows"]
        assert (row["planned"], row["spent"], row["variance"]) == (300.0, 80.0, 220.0)

        body = await _fetch(api_client, budget.id, months=3)
        total = _cat(body, gifts.id)["total"]
        assert D(total["variance"]) == D("220.00") == D(str(result["total_variance"]))
        assert D(body["total_variance"]) == D(body["month_totals"][-2]["cumulative_variance"])
