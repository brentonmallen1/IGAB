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

import pytest

from igab.db.models import BudgetMove
from igab.domain.dates import month_end
from igab.domain.drains import GONE_LABEL, TBA_LABEL
from igab.repositories.import_anchor_repo import anchor_rows
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.services.card_payment import ensure_payment_category
from igab.services.report_service import ReportService
from tests.report_clock import report_today

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


@pytest.fixture(autouse=True)
def _the_service_reads_this_modules_today():
    """Rows are dated from TODAY, read once at import; the report reads the
    clock when called. Pinned, a run that crosses midnight at a month's end
    still asks for the window its rows were seeded in."""
    with report_today(TODAY):
        yield


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


async def _page_available(db_session, budget, category, month) -> Decimal:
    """The Available the Budget page serves for `month` — `get_budget_summary`,
    not `get_category_balance`, which skips the page's card correction."""
    summary = await make_services(db_session).budgets.get_budget_summary(budget.id, month)
    return next(b.available for b in summary.category_balances if b.category_id == category.id)


async def _anchor(db_session, budget, opening_month, available):
    """An import anchor stating YNAB's Available at `opening_month`'s end."""
    db_session.add_all(
        anchor_rows(budget.id, opening_month, available=available, reserve={}, uncovered={})
    )
    await db_session.flush()


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
        # The window, as every other savings report states it. This read []
        # while a budget whose only tagged envelope was deleted read the
        # window: one empty report, two API shapes.
        "months": [months_ago(2), months_ago(1), months_ago(0)],
        # Nothing tagged means nothing to drain from — an empty list, not an
        # absent key, so the report's shape does not change with its contents.
        "drains": {"total": Decimal("0"), "moves": []},
        "unrecovered": [],
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


async def test_an_overspend_before_the_window_is_floored_where_it_happened(db_session):
    """Every other overspend in this suite is inside the window, so a walk
    that lumped the months before it into one opening figure — sum first,
    floor after — passed them all. Five months back the envelope overspent
    by 200 and TBA covered it; four months back it took 500. The lump reads
    100 - 300 + 500 = 300; the Budget page reads 500.
    """
    budget, checking, group, tag_repo = await _setup(db_session)
    fund = await _tagged_category(db_session, budget, group, tag_repo, "Vacation", "savings")
    await create_budget_assignment(db_session, budget, fund, months_ago(5), "100.00")
    await create_transaction(db_session, budget, checking, "-300.00", months_ago(5), category=fund)
    await create_budget_assignment(db_session, budget, fund, months_ago(4), "500.00")

    data = await ReportService(db_session).savings_report(budget.id, months=3)
    row = data["categories"][0]

    assert row["monthly_balances"] == [Decimal("500.00")] * 3
    for month, balance in zip(data["months"], row["monthly_balances"], strict=True):
        assert balance == await _page_available(db_session, budget, fund, month)


async def test_current_balance_equals_the_budget_pages_available(db_session):
    """The differential that covers the whole class of divergence at once.

    Whatever the walk does, this report's Balance and the Budget page's
    Available are the same question about the same envelope, so they must be
    the same number. Asserted against `get_budget_summary` — the figure the
    page serves — rather than a hand-written one, because a hand-written figure
    can agree with both implementations being wrong together. It used to read
    `get_category_balance`, which skips the card correction the page applies,
    so the oracle shared the bug it was meant to catch.
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

    assert report["categories"][0]["current_balance"] == await _page_available(
        db_session, budget, fund, TODAY
    )


async def test_a_row_later_this_month_moves_the_balance_as_it_moves_the_page(db_session):
    """Activity runs to the month's last day, not to today — the Budget page's
    own cutoff (`get_budget_summary` reads the whole month). The report once
    stopped at today, so a posted row dated later this month split the two:
    the report read 500 while the page read 380. Every other fixture date is
    a first of month, so nothing else here can tell the two cutoffs apart.
    """
    last_day = month_end(TODAY)
    if last_day == TODAY:
        pytest.skip("on a month's last day no row can be later this month")
    budget, checking, group, tag_repo = await _setup(db_session)
    fund = await _tagged_category(db_session, budget, group, tag_repo, "Car Repair", "savings")
    await create_budget_assignment(db_session, budget, fund, months_ago(0), "500.00")
    await create_transaction(db_session, budget, checking, "-120.00", last_day, category=fund)

    report = await ReportService(db_session).savings_report(budget.id, months=3)

    assert report["categories"][0]["current_balance"] == Decimal("380.00")
    assert report["categories"][0]["current_balance"] == await _page_available(
        db_session, budget, fund, TODAY
    )


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


@pytest.mark.parametrize("live_sibling", [False, True], ids=["all-filtered", "live-sibling"])
async def test_a_deleted_envelopes_drain_does_not_hang_on_a_live_sibling(db_session, live_sibling):
    """Drains read every tagged envelope, a deleted one included: the move
    happened while it was savings. When the deleted one was the only tagged
    envelope, an early return served an empty report without them — so a
    40.00 move out of "Old Goal" showed while "Emergency Fund" was tagged and
    vanished when it was not.
    """
    budget, checking, group, tag_repo = await _setup(db_session)
    if live_sibling:
        live = await _tagged_category(
            db_session, budget, group, tag_repo, "Emergency Fund", "savings"
        )
        await create_budget_assignment(db_session, budget, live, months_ago(0), "200.00")
    gone = await _tagged_category(db_session, budget, group, tag_repo, "Old Goal", "savings")
    await create_budget_assignment(db_session, budget, gone, months_ago(1), "90.00")
    db_session.add(
        BudgetMove(
            budget_id=budget.id,
            month=months_ago(1),
            from_category_id=gone.id,
            to_category_id=None,
            amount=Decimal("40.00"),
        )
    )
    gone.is_deleted = True
    await db_session.flush()

    data = await ReportService(db_session).savings_report(budget.id, months=3)

    assert data["months"] == [months_ago(2), months_ago(1), months_ago(0)]
    assert data["summary"]["category_count"] == (1 if live_sibling else 0)
    assert data["drains"]["total"] == Decimal("40.00")
    assert [(m["from_name"], m["to_name"], m["amount"]) for m in data["drains"]["moves"]] == [
        (GONE_LABEL, TBA_LABEL, Decimal("40.00"))
    ]


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


async def test_an_imported_budget_walks_back_from_ynabs_figure(db_session):
    """The anchored walk starts at the import and says nothing earlier, so
    every month before it read 0 — a flat line that jumped to the whole
    balance at the import, beside an Inflow column counting those months'
    deposits. The months before are walked back from YNAB's own figure.
    """
    budget, checking, group, tag_repo = await _setup(db_session)
    fund = await _tagged_category(db_session, budget, group, tag_repo, "Emergency Fund", "savings")
    for n in range(6, 1, -1):
        await create_budget_assignment(db_session, budget, fund, months_ago(n), "200.00")
    await create_budget_assignment(db_session, budget, fund, months_ago(0), "50.00")
    await _anchor(db_session, budget, months_ago(2), {fund.id: Decimal("1000.00")})

    data = await ReportService(db_session).savings_report(budget.id, months=6)
    row = data["categories"][0]

    # 1000 at the import, 200 a month before it; then the anchored months.
    # Before: [0, 0, 0, 1000, 1000, 1050].
    assert row["monthly_balances"] == [
        Decimal("400.00"),
        Decimal("600.00"),
        Decimal("800.00"),
        Decimal("1000.00"),
        Decimal("1000.00"),
        Decimal("1050.00"),
    ]
    assert data["unrecovered"] == []
    assert row["current_balance"] == await _page_available(db_session, budget, fund, TODAY)


async def test_an_envelope_whose_history_cannot_reach_ynabs_figure_starts_late(db_session):
    """YNAB ended the import month at 100 though that month alone assigned
    200 — spending YNAB saw that the register does not hold. No earlier
    balance can be walked back from that, so the line starts at the import
    and the report says why instead of drawing a gap nobody explained.
    """
    budget, checking, group, tag_repo = await _setup(db_session)
    fund = await _tagged_category(db_session, budget, group, tag_repo, "Vacation", "savings")
    await create_budget_assignment(db_session, budget, fund, months_ago(5), "100.00")
    await create_budget_assignment(db_session, budget, fund, months_ago(2), "200.00")
    await create_budget_assignment(db_session, budget, fund, months_ago(0), "50.00")
    await _anchor(db_session, budget, months_ago(2), {fund.id: Decimal("100.00")})

    data = await ReportService(db_session).savings_report(budget.id, months=6)

    assert data["categories"][0]["monthly_balances"] == [
        None,
        None,
        None,
        Decimal("100.00"),
        Decimal("100.00"),
        Decimal("150.00"),
    ]
    assert data["unrecovered"] == [
        {"category_id": str(fund.id), "category_name": "Vacation", "starts_from": months_ago(2)}
    ]


async def test_a_card_refund_reads_as_the_budget_page_does(db_session):
    """Nothing assigned, so a $100 card charge rode the card as debt; the
    refund repaid that debt and handed the envelope nothing. The Budget page
    takes that repayment back out inside its walk. This report re-derived
    Available without the step and read $100 above the page from the refund on.
    """
    budget, checking, group, tag_repo = await _setup(db_session)
    visa = await create_account(db_session, budget, "Sapphire Visa", account_type="credit_card")
    await ensure_payment_category(db_session, visa)
    fund = await _tagged_category(
        db_session, budget, group, tag_repo, "Car Repair", "long_term_expense"
    )
    await create_transaction(
        db_session, budget, visa, "-100.00", months_ago(2).replace(day=9), category=fund
    )
    await create_transaction(
        db_session, budget, visa, "100.00", months_ago(1).replace(day=9), category=fund
    )
    await create_budget_assignment(db_session, budget, fund, months_ago(0), "40.00")

    data = await ReportService(db_session).savings_report(budget.id, months=3)
    row = data["categories"][0]

    # Before: [-100, 100, 140].
    assert row["monthly_balances"] == [Decimal("-100.00"), Decimal("0.00"), Decimal("40.00")]
    for month, balance in zip(data["months"], row["monthly_balances"], strict=True):
        assert balance == await _page_available(db_session, budget, fund, month)
