"""Savings report: envelope balances over time for savings-tagged categories.

**The balance is the envelope's Available, computed by `domain.carryover`** —
the same walk the Budget page uses, floored between months. This suite used to
enshrine the opposite: "running balance = prior balance ... then, month by
month, + assigned + activity". That is not an envelope balance. A month that
ends negative is covered from To Be Assigned and the next month starts at zero,
so a savings envelope once overspent used to carry its overspend forward
forever and the report's Balance column disagreed with the Available shown for
the same envelope on the Budget page — the one number this report exists to
state. The old walk also ignored the import anchor, so every YNAB-imported
budget was wrong from its first month.

`total_inflow` counts only positive assignments in the window. The window for
`months=N` is N entries; it used to be N+1, so "All time (18 months)" drew 19
columns with an empty leader and divided the average inflow by 19.
"""

from datetime import date
from decimal import Decimal

from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.report_service import ReportService

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

TODAY = date.today()


def months_ago(n: int) -> date:
    year, month = TODAY.year, TODAY.month - n
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


async def _setup(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    group = await create_category_group(db_session, budget, "Goals")
    await seed_system_tags(db_session, budget.id)
    tag_repo = TagRepository(db_session)
    return budget, checking, group, tag_repo


async def _tagged_category(db_session, budget, group, tag_repo, name, system_key):
    category = await create_category(db_session, budget, group, name)
    tag = await tag_repo.get_system_tag(budget.id, system_key)
    await tag_repo.set_category_tags(category.id, [tag.id])
    return category


async def test_balances_carry_prior_history_then_accumulate_monthly(db_session):
    budget, checking, group, tag_repo = await _setup(db_session)
    ef = await _tagged_category(db_session, budget, group, tag_repo, "Emergency Fund", "savings")
    lt = await _tagged_category(
        db_session, budget, group, tag_repo, "New Roof", "long_term_expense"
    )

    # Prior history (before the 3-month window): 1000 assigned, 100 spent
    await create_budget_assignment(db_session, budget, ef, months_ago(5), "1000.00")
    await create_transaction(db_session, budget, checking, "-100.00", months_ago(5), category=ef)
    # In-window: two deposits, one withdrawal
    await create_budget_assignment(db_session, budget, ef, months_ago(2), "500.00")
    await create_budget_assignment(db_session, budget, ef, months_ago(1), "500.00")
    await create_transaction(db_session, budget, checking, "-200.00", months_ago(1), category=ef)
    # long_term_expense categories belong in the report too
    await create_budget_assignment(db_session, budget, lt, months_ago(0), "250.00")

    data = await ReportService(db_session).savings_report(budget.id, months=3)

    assert data["months"] == [months_ago(2), months_ago(1), months_ago(0)]
    by_name = {c["category_name"]: c for c in data["categories"]}

    # 1000 assigned less 100 spent five months ago ends that month at 900,
    # which carries in; then +500, then +500 less 200; the current month has no
    # data of its own so it reads the carried 1700.
    ef_row = by_name["Emergency Fund"]
    assert ef_row["monthly_balances"] == [
        Decimal("1400.00"),
        Decimal("1700.00"),
        Decimal("1700.00"),
    ]
    assert ef_row["current_balance"] == Decimal("1700.00")
    assert ef_row["total_inflow"] == Decimal("1000.00")

    lt_row = by_name["New Roof"]
    assert lt_row["monthly_balances"] == [
        Decimal("0"),
        Decimal("0"),
        Decimal("250.00"),
    ]
    assert lt_row["total_inflow"] == Decimal("250.00")

    # Sorted by current balance descending
    assert [c["category_name"] for c in data["categories"]] == ["Emergency Fund", "New Roof"]

    summary = data["summary"]
    assert summary["total_balance"] == Decimal("1950.00")
    assert summary["total_inflow"] == Decimal("1250.00")
    assert summary["avg_monthly_inflow"] == Decimal("416.67")  # 1250 / 3 window months
    assert summary["category_count"] == 2


async def test_negative_assignment_reduces_balance_but_not_inflow(db_session):
    budget, checking, group, tag_repo = await _setup(db_session)
    fund = await _tagged_category(db_session, budget, group, tag_repo, "Vacation", "savings")

    await create_budget_assignment(db_session, budget, fund, months_ago(1), "500.00")
    await create_budget_assignment(db_session, budget, fund, months_ago(0), "-300.00")

    data = await ReportService(db_session).savings_report(budget.id, months=3)

    row = data["categories"][0]
    assert row["monthly_balances"] == [
        Decimal("0"),
        Decimal("500.00"),
        Decimal("200.00"),
    ]
    # Money moved OUT via a negative assignment is not an inflow
    assert row["total_inflow"] == Decimal("500.00")
    assert data["summary"]["total_inflow"] == Decimal("500.00")


async def test_pending_and_deleted_excluded_split_child_counted(db_session):
    budget, checking, group, tag_repo = await _setup(db_session)
    fund = await _tagged_category(db_session, budget, group, tag_repo, "Sink Fund", "savings")

    parent = await create_transaction(
        db_session, budget, checking, "-50.00", months_ago(0), is_split=True
    )
    await create_transaction(
        db_session,
        budget,
        checking,
        "-20.00",
        months_ago(0),
        category=fund,
        parent_transaction_id=parent.id,
    )
    await create_transaction(
        db_session, budget, checking, "-10.00", months_ago(0), category=fund, cleared="pending"
    )
    await create_transaction(
        db_session, budget, checking, "-5.00", months_ago(0), category=fund, is_deleted=True
    )

    data = await ReportService(db_session).savings_report(budget.id, months=3)

    row = data["categories"][0]
    # Only the split child's -20 is real posted activity
    assert row["monthly_balances"][-1] == Decimal("-20.00")
    assert row["current_balance"] == Decimal("-20.00")


async def test_no_tagged_categories_is_empty(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)

    data = await ReportService(db_session).savings_report(budget.id, months=3)

    assert data == {
        "categories": [],
        "summary": {
            "total_balance": Decimal("0"),
            "total_inflow": Decimal("0"),
            "avg_monthly_inflow": Decimal("0"),
            "category_count": 0,
        },
        "months": [],
        # Nothing tagged means nothing to drain from — an empty list, not an
        # absent key, so the report's shape does not change with its contents.
        "drains": {"total": Decimal("0"), "moves": []},
    }


async def test_a_month_that_overspent_hands_zero_to_the_next(db_session):
    """The zero floor, which the old running total did not have.

    A month that ends negative is covered from To Be Assigned; the next month
    starts at zero. Only the month with its own data may read negative. The
    running total carried the overspend forward forever instead.
    """
    budget, checking, group, tag_repo = await _setup(db_session)
    fund = await _tagged_category(db_session, budget, group, tag_repo, "Vacation", "savings")

    await create_budget_assignment(db_session, budget, fund, months_ago(2), "300.00")
    await create_transaction(db_session, budget, checking, "-500.00", months_ago(2), category=fund)
    await create_budget_assignment(db_session, budget, fund, months_ago(1), "300.00")
    await create_budget_assignment(db_session, budget, fund, months_ago(0), "300.00")

    data = await ReportService(db_session).savings_report(budget.id, months=3)
    row = data["categories"][0]

    # -200 is absorbed by TBA, so the next month opens at 0, not at -200.
    # The running total answered [-200.00, 100.00, 400.00].
    assert row["monthly_balances"] == [
        Decimal("-200.00"),
        Decimal("300.00"),
        Decimal("600.00"),
    ]
    assert row["current_balance"] == Decimal("600.00")


async def test_current_balance_equals_the_budget_pages_available(db_session):
    """The differential that covers the whole class of divergence at once.

    Whatever the walk does, this report's Balance and the Budget page's
    Available are the same question about the same envelope, so they must be
    the same number. Asserted against `BudgetService.get_category_balance`
    rather than a hand-written figure, because a hand-written figure can agree
    with both implementations being wrong together.
    """
    budget, checking, group, tag_repo = await _setup(db_session)
    fund = await _tagged_category(db_session, budget, group, tag_repo, "New Roof", "savings")

    # A history with an overspend in it, so the floor is load-bearing.
    await create_budget_assignment(db_session, budget, fund, months_ago(4), "400.00")
    await create_transaction(db_session, budget, checking, "-650.00", months_ago(4), category=fund)
    await create_budget_assignment(db_session, budget, fund, months_ago(2), "250.00")
    await create_transaction(db_session, budget, checking, "-90.00", months_ago(1), category=fund)
    await create_budget_assignment(db_session, budget, fund, months_ago(0), "175.00")

    report = await ReportService(db_session).savings_report(budget.id, months=6)
    grid = await make_services(db_session).budgets.get_category_balance(fund.id, TODAY)

    assert report["categories"][0]["current_balance"] == grid.available


async def test_activity_on_an_off_budget_account_moves_neither_figure(db_session):
    """The activity query omitted ON_BUDGET_ACCOUNT, so a categorized row on a
    tracking account moved this report's balance and not the grid's.

    `sum_all_categories_by_month` carries the predicate and says the two "must
    stay predicate-identical", so reading through it is the fix.
    """
    budget, checking, group, tag_repo = await _setup(db_session)
    fund = await _tagged_category(db_session, budget, group, tag_repo, "Brokerage", "savings")
    tracked = await create_account(db_session, budget, "Cascade Point HYSA", on_budget=False)

    await create_budget_assignment(db_session, budget, fund, months_ago(0), "500.00")
    await create_transaction(db_session, budget, tracked, "-120.00", months_ago(0), category=fund)

    report = await ReportService(db_session).savings_report(budget.id, months=3)
    grid = await make_services(db_session).budgets.get_category_balance(fund.id, TODAY)

    # The off-budget row is not budget activity: 500, not 380.
    assert report["categories"][0]["current_balance"] == Decimal("500.00")
    assert report["categories"][0]["current_balance"] == grid.available


async def test_a_soft_deleted_envelope_is_not_a_row(db_session):
    """A tag outlives the category it was on. The envelope set was the raw tag
    lookup, so a soft-deleted category became a row, carried the assignments it
    once held as a balance, and counted toward `category_count`.
    """
    budget, checking, group, tag_repo = await _setup(db_session)
    live = await _tagged_category(db_session, budget, group, tag_repo, "Emergency Fund", "savings")
    gone = await _tagged_category(db_session, budget, group, tag_repo, "Old Goal", "savings")

    await create_budget_assignment(db_session, budget, live, months_ago(0), "200.00")
    await create_budget_assignment(db_session, budget, gone, months_ago(1), "900.00")
    gone.is_deleted = True
    await db_session.flush()

    data = await ReportService(db_session).savings_report(budget.id, months=3)

    assert [c["category_name"] for c in data["categories"]] == ["Emergency Fund"]
    assert data["summary"]["category_count"] == 1
    assert data["summary"]["total_balance"] == Decimal("200.00")


async def test_the_window_has_exactly_the_months_asked_for(db_session):
    """`months=N` is N buckets. It used to be N+1, so the picker's
    "All time (N months)" drew a leading empty column and the average inflow
    was divided by N+1.
    """
    budget, checking, group, tag_repo = await _setup(db_session)
    fund = await _tagged_category(db_session, budget, group, tag_repo, "Vacation", "savings")
    await create_budget_assignment(db_session, budget, fund, months_ago(0), "600.00")

    data = await ReportService(db_session).savings_report(budget.id, months=6)

    assert len(data["months"]) == 6
    assert data["months"] == [months_ago(n) for n in range(5, -1, -1)]
    assert len(data["categories"][0]["monthly_balances"]) == 6
    assert data["summary"]["avg_monthly_inflow"] == Decimal("100.00")  # 600 / 6
