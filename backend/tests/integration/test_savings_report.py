"""Savings report: envelope balances over time for savings-tagged categories.

Balance semantics pinned here: running balance = prior balance (all
assignments + posted activity before the window) then, month by month,
+ assigned + activity. `total_inflow` counts only positive assignments in
the window. The window for `months=N` is N+1 entries (N months back through
the current month).
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
    await create_transaction(
        db_session, budget, checking, "-100.00", months_ago(5), category=ef
    )
    # In-window: two deposits, one withdrawal
    await create_budget_assignment(db_session, budget, ef, months_ago(2), "500.00")
    await create_budget_assignment(db_session, budget, ef, months_ago(1), "500.00")
    await create_transaction(
        db_session, budget, checking, "-200.00", months_ago(1), category=ef
    )
    # long_term_expense categories belong in the report too
    await create_budget_assignment(db_session, budget, lt, months_ago(0), "250.00")

    data = await ReportService(db_session).savings_report(budget.id, months=3)

    assert data["months"] == [months_ago(3), months_ago(2), months_ago(1), months_ago(0)]
    by_name = {c["category_name"]: c for c in data["categories"]}

    ef_row = by_name["Emergency Fund"]
    assert ef_row["monthly_balances"] == [
        Decimal("900.00"),
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
        Decimal("0"),
        Decimal("250.00"),
    ]
    assert lt_row["total_inflow"] == Decimal("250.00")

    # Sorted by current balance descending
    assert [c["category_name"] for c in data["categories"]] == ["Emergency Fund", "New Roof"]

    summary = data["summary"]
    assert summary["total_balance"] == Decimal("1950.00")
    assert summary["total_inflow"] == Decimal("1250.00")
    assert summary["avg_monthly_inflow"] == Decimal("312.50")  # 1250 / 4 window months
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
    }
