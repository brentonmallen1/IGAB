"""Plan vs Spent: what each category had, spent and had left per month, with a
total per month and per category.

Carryover counts (`domain.plan`, owner's call 2026-09-28): a month carries in
what the one before left, floored as the budget page carries it, and `left` is
the budget page's Available. A month is over only when the envelope went
negative — the budget page's red, which Ready to Assign covered. It used to
judge each month's assignment alone, so an envelope funded once and spent over
several months read over plan in every one of them.

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
    assert D(prev["carried_in"]) == D("0")
    assert D(prev["assigned"]) == D("200.00")
    assert D(prev["funded"]) == D("200.00")
    assert D(prev["spent"]) == D("150.00")
    assert D(prev["left"]) == D("50.00")
    # The running month's cell is drawn, month-to-date, carrying in the 50:
    # 50 + 100 - 130 leaves 20. Judged alone it read 30 over.
    cur = _cell(cat, m0)
    assert (D(cur["carried_in"]), D(cur["funded"]), D(cur["left"])) == (
        D("50.00"),
        D("150.00"),
        D("20.00"),
    )
    assert cur["over"] is False
    # Empty months are zero-filled so the frontend gets a full grid
    empty = _cell(cat, _months_back(4))
    assert (D(empty["assigned"]), D(empty["spent"]), D(empty["left"])) == (D("0"), D("0"), D("0"))
    assert empty["active"] is False

    # ...and counted in no verdict or total: those are the complete months'.
    assert cat["months_active"] == 1
    assert cat["months_over"] == 0
    assert D(cat["total"]["assigned"]) == D("200.00")
    assert D(cat["total"]["funded"]) == D("200.00")
    assert D(cat["total"]["spent"]) == D("150.00")
    assert D(cat["total"]["left"]) == D("50.00")
    assert D(body["total_assigned"]) == D("200.00")
    assert D(body["total_spent"]) == D("150.00")
    assert D(body["total_left"]) == D("50.00")
    # The totals row: last month is its one cell; the running month is drawn
    # with its own figures so far.
    by_month = {t["month"]: t for t in body["month_totals"]}
    assert D(by_month[m1.isoformat()]["funded"]) == D("200.00")
    assert D(by_month[m1.isoformat()]["left"]) == D("50.00")
    assert by_month[m0.isoformat()]["partial_month"] is True
    assert D(by_month[m0.isoformat()]["spent"]) == D("130.00")
    assert D(by_month[m0.isoformat()]["left"]) == D("20.00")


async def test_carryover_counts(api_client, db_session):
    """Assigned once, spent for three months. The months without an
    assignment used to read over plan by what they spent, although the
    envelope still had money; each now carries in what the month before left
    and is on plan."""
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
    assert entry["months_over"] == 0
    # 300 - 50 = 250; 250 - 50 = 200; 200 - 50 = 150.
    for n, carried, left in ((2, "0", "250"), (1, "250", "200"), (0, "200", "150")):
        cell = _cell(entry, _months_back(n))
        assert (D(cell["carried_in"]), D(cell["spent"]), D(cell["left"])) == (
            D(carried),
            D("50"),
            D(left),
        ), n
        assert cell["over"] is False
    # The Total column over the complete months: nothing carried in, 300
    # funded, 100 spent, 200 left.
    total = entry["total"]
    assert (D(total["carried_in"]), D(total["funded"]), D(total["spent"])) == (
        D("0"),
        D("300"),
        D("100"),
    )
    assert (D(total["left"]), D(total["overspent"]), total["over"]) == (D("200"), D("0"), False)


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
    reduced, not a household overspending. Drain 300 a month from an envelope
    that spent nothing and `0 > -300` flagged every month; do it in three of
    the last six and the report named that envelope the household's worst
    habit, with no spending in it at all.

    With carryover counting, the drains come out of the 900 funded before
    them: 600, 300, then 0 left, never negative, never over.
    """
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Goals")
    drained = await create_category(db_session, budget, group, "Car Repairs")

    await _history_from(db_session, budget, account, 6)
    await create_budget_assignment(db_session, budget, drained, _months_back(3), "900.00")
    for n in (0, 1, 2):
        await create_budget_assignment(db_session, budget, drained, _months_back(n), "-300.00")
    await db_session.commit()

    body = await _fetch(api_client, budget.id, months=6)

    assert body["chronic_count"] == 0
    row = _cat(body, drained.id)
    assert row["months_over"] == 0
    assert not row["chronic"]
    for n, left in ((3, "900"), (2, "600"), (1, "300"), (0, "0")):
        cell = _cell(row, _months_back(n))
        assert cell["active"] is True, n
        assert (D(cell["left"]), D(cell["overspent"]), cell["over"]) == (D(left), D("0"), False)


async def test_draining_money_an_envelope_never_had_is_the_budget_pages_red(db_session, api_client):
    """The other side of the same rule. Taking 300 back out of an envelope
    that holds nothing leaves the budget page at -300, and Ready to Assign
    covers it — so this report, which reads the page's Available, calls that
    month 300 overspent. It used to floor the plan at zero and call it on plan,
    which is not what the page showed."""
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Goals")
    drained = await create_category(db_session, budget, group, "Car Repairs")
    await _history_from(db_session, budget, account, 3)
    await create_budget_assignment(db_session, budget, drained, _months_back(1), "-300.00")
    await db_session.commit()

    body = await _fetch(api_client, budget.id, months=3)
    cell = _cell(_cat(body, drained.id), _months_back(1))

    assert (D(cell["funded"]), D(cell["spent"]), D(cell["left"])) == (
        D("-300"),
        D("0"),
        D("-300"),
    )
    assert (D(cell["overspent"]), cell["over"]) == (D("300"), True)


async def test_real_overspending_of_a_drained_envelope_still_counts(db_session, api_client):
    """Draining must not hide genuine overspending: 300 funded, all 300 taken
    back out, then 120 spent — the envelope ends 120 negative and is over by
    120, not by the 420 an unfloored `assigned - spent` ranked it by.
    """
    budget = await create_budget(db_session, api_client.test_user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Goals")
    cat_obj = await create_category(db_session, budget, group, "Car Repairs")

    await _history_from(db_session, budget, checking, 6)
    last = _months_back(1)
    await create_budget_assignment(db_session, budget, cat_obj, _months_back(2), "300.00")
    await create_budget_assignment(db_session, budget, cat_obj, last, "-300.00")
    await create_transaction(
        db_session, budget, checking, "-120.00", last.replace(day=10), category=cat_obj
    )
    await db_session.commit()

    body = await _fetch(api_client, budget.id, months=6)
    cat = _cat(body, cat_obj.id)

    assert cat["months_over"] == 1
    assert D(cat["avg_overspend"]) == D("120.00")
    cell = _cell(cat, last)
    assert (D(cell["carried_in"]), D(cell["funded"]), D(cell["left"])) == (
        D("300"),
        D("0"),
        D("-120"),
    )
    assert D(cell["overspent"]) == D("120.00")


class TestTheTotalColumnGivesTheCellsVerdict:
    """The Total column was Budget vs Actual, which answered the same question
    over a window and did not floor: it served `assigned - spent` raw, and its
    chart decided overspent for itself from `spent > assigned`. Over one
    drained envelope the two reports gave opposite verdicts — neutral on the
    matrix, a red 300 overrun beside it, and quoted to the AI as -300. Both
    now walk the same months (`domain.plan.across_months`), and they are one
    response."""

    async def _drained(self, db_session, api_client, spent: str | None):
        """300 funded two months ago, all of it taken back out last month, and
        optionally `spent` last month on top."""
        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Goals")
        drained = await create_category(db_session, budget, group, "Car Repairs")
        await _history_from(db_session, budget, checking, 3)
        last = _months_back(1)
        await create_budget_assignment(db_session, budget, drained, _months_back(2), "300.00")
        await create_budget_assignment(db_session, budget, drained, last, "-300.00")
        if spent is not None:
            await create_transaction(
                db_session, budget, checking, spent, last.replace(day=10), category=drained
            )
        await db_session.commit()
        body = await _fetch(api_client, budget.id, months=3)
        return body, _cat(body, drained.id), last

    async def test_a_drained_envelope_is_on_plan_in_its_cell_and_its_total(
        self, db_session, api_client
    ):
        body, row, last = await self._drained(db_session, api_client, None)
        total = row["total"]
        # 300 funded and 300 taken back: funded 0 over the span, 0 left.
        assert (D(total["funded"]), D(total["left"]), D(total["overspent"])) == (
            D("0"),
            D("0"),
            D("0"),
        )
        assert total["over"] is False
        cell = _cell(row, last)
        assert (cell["active"], cell["over"], D(cell["left"])) == (True, False, D("0"))
        assert (D(body["total_overspent"]), D(body["total_left"])) == (D("0"), D("0"))

    async def test_real_spending_is_over_by_the_same_amount_in_both(self, db_session, api_client):
        body, row, last = await self._drained(db_session, api_client, "-120.00")
        total = row["total"]

        assert total["over"] is True
        # 120, not the 420 the unfloored subtraction ranked it by.
        assert D(total["overspent"]) == D("120.00")
        assert D(_cell(row, last)["overspent"]) == D("120.00")
        # funded 0 - spent 120 + other 0 + overspent 120 == left 0.
        assert (D(total["funded"]), D(total["spent"]), D(total["left"])) == (
            D("0"),
            D("120"),
            D("0"),
        )
        # And the headline says the same. It was raw assigned - spent, -420
        # here, above a row reading -120.
        assert D(body["total_overspent"]) == D("120.00")


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
    for, widened to whole months: an assignment is a month's, so half a
    month's spending against the month's whole assignment would read under."""

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
        # in the second month — after the day the range names, so a range read
        # as named would miss it.
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
        # Month by month: 300 left, then 300 carried in, 300 swept out and 80
        # spent — the envelope ends at -80, which Ready to Assign covered.
        (row,) = result["rows"]
        assert (row["carried_in"], row["funded"], row["spent"]) == (0.0, 0.0, 80.0)
        assert (row["left"], row["overspent"]) == (0.0, 80.0)

        body = await _fetch(api_client, budget.id, months=3)
        total = _cat(body, gifts.id)["total"]
        assert D(total["overspent"]) == D("80.00") == D(str(result["total_overspent"]))
        assert D(body["total_overspent"]) == D(body["month_totals"][-2]["overspent"])


class TestLeftIsTheBudgetPagesAvailable:
    """The differential test `domain.plan.EnvelopeOutcome.other` points at.

    Every cell's `left` is served from `BudgetService.envelope_series`, and
    this holds it to the page's single-category walk,
    `BudgetService.get_category_balance`, over the situations where a
    re-derived balance would drift from the page: a month that overspent (the
    next starts from zero, not from the debt), an envelope funded before the
    window (it carries in what it held), and an import-anchored envelope (it
    starts from YNAB's figure, not from a history that never reproduced it).

    Invented figures, over the last three complete months and the running one:

    - Groceries: 200 in, 260 spent (ends -60); 200 in, 150 spent (starts from
      0, ends 50); 100 in, 120 spent (30); 10 spent this month (20).
    - Car Fund: 600 assigned the month before the window, 100 spent in the
      first and third months — 500, 500, 400, 400.
    - Vacation: anchored at 120 by an import two months before the window;
      100 in, then 80 spent — 220, 140, 140, 140.
    """

    async def _world(self, db_session, api_client):
        from igab.db.models import ImportAnchor

        budget = await create_budget(db_session, api_client.test_user)
        checking = await create_account(db_session, budget, "Checking")
        group = await create_category_group(db_session, budget, "Everyday")
        groceries = await create_category(db_session, budget, group, "Groceries")
        car = await create_category(db_session, budget, group, "Car Fund")
        vacation = await create_category(db_session, budget, group, "Vacation")

        anchor_month = _months_back(5)
        db_session.add(
            ImportAnchor(
                budget_id=budget.id,
                month=anchor_month,
                kind="available",
                category_id=vacation.id,
                amount=D("120.00"),
            )
        )
        # The history starts in the anchor month, with a row no envelope sees.
        await _history_from(db_session, budget, checking, 5)

        async def spend(cat, n: int, amount: str) -> None:
            await create_transaction(
                db_session, budget, checking, amount, _months_back(n), category=cat
            )

        for n, assigned, spent in ((3, "200.00", "-260.00"), (2, "200.00", "-150.00")):
            await create_budget_assignment(db_session, budget, groceries, _months_back(n), assigned)
            await spend(groceries, n, spent)
        await create_budget_assignment(db_session, budget, groceries, _months_back(1), "100.00")
        await spend(groceries, 1, "-120.00")
        await spend(groceries, 0, "-10.00")

        await create_budget_assignment(db_session, budget, car, _months_back(4), "600.00")
        await spend(car, 3, "-100.00")
        await spend(car, 1, "-100.00")

        await create_budget_assignment(db_session, budget, vacation, _months_back(3), "100.00")
        await spend(vacation, 2, "-80.00")
        await db_session.commit()

        body = await _fetch(api_client, budget.id, months=3)
        return budget, body, {"Groceries": groceries, "Car Fund": car, "Vacation": vacation}

    async def test_every_cell_left_is_the_budget_pages_available(self, db_session, api_client):
        from igab.domain.carryover import next_carryover
        from igab.guide.detection import budget_service_from

        _, body, cats = await self._world(db_session, api_client)
        page = budget_service_from(db_session)

        checked = 0
        for cat in cats.values():
            row = _cat(body, cat.id)
            before = await page.get_category_balance(cat.id, _months_back(4))
            assert D(row["monthly"][0]["carried_in"]) == next_carryover(before.available)
            for cell in row["monthly"]:
                month = date.fromisoformat(cell["month"])
                balance = await page.get_category_balance(cat.id, month)
                assert D(cell["left"]) == balance.available, (cat.name, month)
                assert cell["estimated"] is False
                checked += 1
        assert checked == 12

    async def test_the_figures_the_fixture_was_written_to_reach(self, db_session, api_client):
        """The same cells against the figures worked on paper above, so the
        differential cannot pass by both sides being wrong together."""
        _, body, cats = await self._world(db_session, api_client)

        def lefts(name):
            return [D(c["left"]) for c in _cat(body, cats[name].id)["monthly"]]

        assert lefts("Groceries") == [D("-60"), D("50"), D("30"), D("20")]
        assert lefts("Car Fund") == [D("500"), D("500"), D("400"), D("400")]
        assert lefts("Vacation") == [D("220"), D("140"), D("140"), D("140")]

        groceries = _cat(body, cats["Groceries"].id)
        overspent, recovered = groceries["monthly"][0], groceries["monthly"][1]
        assert (D(overspent["overspent"]), overspent["over"]) == (D("60"), True)
        # Ready to Assign covered the 60: the next month starts from nothing.
        assert D(recovered["carried_in"]) == D("0")
        # Total: 0 carried in, 500 funded, 530 spent, 60 covered, 30 left.
        total = groceries["total"]
        assert [D(total[k]) for k in ("carried_in", "funded", "spent", "overspent", "left")] == [
            D("0"),
            D("500"),
            D("530"),
            D("60"),
            D("30"),
        ]

        car = _cat(body, cats["Car Fund"].id)
        # Funded before the window, it carries in the 600 and is never over.
        assert D(car["monthly"][0]["carried_in"]) == D("600")
        assert car["months_over"] == 0
        assert [D(car["total"][k]) for k in ("carried_in", "funded", "spent", "left")] == [
            D("600"),
            D("600"),
            D("200"),
            D("400"),
        ]

        vacation = _cat(body, cats["Vacation"].id)
        # The import's 120 is what it carried into the window.
        assert D(vacation["monthly"][0]["carried_in"]) == D("120")
        assert D(vacation["monthly"][0]["funded"]) == D("220")

    async def test_an_ordinary_envelope_has_nothing_other(self, db_session, api_client):
        """`other` is what the page's Available counts and the plan ledger does
        not — a pending row, a starting balance, a card refund repaying debt.
        None of those is here, so every cell and every total holds
        `funded - spent == left` exactly."""
        _, body, cats = await self._world(db_session, api_client)

        for cat in cats.values():
            row = _cat(body, cat.id)
            for cell in row["monthly"]:
                assert D(cell["other"]) == D("0"), (cat.name, cell["month"])
                assert D(cell["funded"]) - D(cell["spent"]) == D(cell["left"])
            assert D(row["total"]["other"]) == D("0"), cat.name
        assert D(body["total_other"]) == D("0")
