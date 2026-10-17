"""Two "average spent" figures, and exactly how far apart they may be.

Auto-assign's "Average spent" (`BudgetService.get_category_history`) and the
Category History report's (`plan_ledger.spent_series`, which the target
editor's suggestions read too) answer different questions — what assignments
had to cover, and what was spent — and the differences are deliberate and
listed at both definitions:

1. money moved in nets the history figure and is not spending in the ledger;
2. a month that took in more than it paid out is zero in the history figure,
   negative in the ledger;
3. the history divides by the envelope's own active months, the ledger by
   every complete month of the window.

On plain spending the two read the same months and the same total. These
tests hold them to that, and to exactly the three differences: any further
drift fails here. Amounts are invented and round.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import update

from igab.db.models import Transaction
from igab.domain.dates import ReportWindow, month_starts
from igab.services.plan_ledger import spent_series

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
    make_services,
)

D = Decimal
TODAY = date(2026, 8, 15)
CURRENT = date(2026, 8, 1)
# The six complete months both figures read from TODAY.
WINDOW = ReportWindow(tuple(month_starts(date(2026, 2, 1), date(2026, 7, 31))), CURRENT)
MAY, JUNE, JULY = date(2026, 5, 3), date(2026, 6, 3), date(2026, 7, 3)


async def _world(db_session, user):
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    hysa = await create_account(
        db_session, budget, "Cascade Point HYSA", account_type="savings", on_budget=False
    )
    group = await create_category_group(db_session, budget, "Everyday")
    return make_services(db_session), budget, checking, hysa, group


async def _both(db_session, services, budget, category):
    history = await services.budgets.get_category_history(budget.id, category.id, CURRENT)
    ledger = await spent_series(db_session, budget.id, category.id, WINDOW, TODAY)
    complete_total = sum(ledger.spent[: len(WINDOW.complete)], D("0"))
    return history, ledger, complete_total


async def test_plain_spending_reads_the_same_total_and_differs_only_in_the_divisor(
    db_session, api_client
):
    """100 in May, 80 less a 20 refund in June, 140 in July: 300 in all.
    The history divides by its three active months, the ledger by six."""
    services, budget, checking, _, group = await _world(db_session, api_client.test_user)
    groceries = await create_category(db_session, budget, group, "Groceries")
    for amount, day in (("-100", MAY), ("-80", JUNE), ("20", JUNE), ("-140", JULY)):
        await create_transaction(db_session, budget, checking, amount, day, category=groceries)

    history, ledger, total = await _both(db_session, services, budget, groceries)

    assert total == D("300")
    assert (history.average_spent, history.months_included) == (D("100.00"), 3)
    assert (ledger.average_spent, ledger.months_averaged) == (D("50.00"), 6)
    assert history.average_spent * history.months_included == total
    assert history.last_month_spent == ledger.spent[len(WINDOW.complete) - 1] == D("140")


async def test_money_moved_in_is_the_only_gap_in_the_total(db_session, api_client):
    """June: 2,000 moved in from savings paid a 2,000 bill; July: a 300 bill.
    The ledger spent 2,300; assignments had to cover 300 — the gap is the
    2,000 moved in, and nothing else."""
    services, budget, checking, hysa, group = await _world(db_session, api_client.test_user)
    medical = await create_category(db_session, budget, group, "Medical")
    _, to_leg = await create_transfer(db_session, budget, hysa, checking, "2000.00", JUNE)
    await db_session.execute(
        update(Transaction).where(Transaction.id == to_leg.id).values(category_id=medical.id)
    )
    await db_session.flush()
    await create_transaction(db_session, budget, checking, "-2000", JUNE, category=medical)
    await create_transaction(db_session, budget, checking, "-300", JULY, category=medical)

    history, ledger, total = await _both(db_session, services, budget, medical)

    moved_in = sum(ledger.moved_in[: len(WINDOW.complete)], D("0"))
    assert (total, moved_in) == (D("2300"), D("2000"))
    # June netted to nothing, so it is not one of the history's months.
    assert (history.average_spent, history.months_included) == (D("300.00"), 1)
    assert history.average_spent * history.months_included == total - moved_in


async def test_a_month_of_net_refunds_is_zero_in_one_and_negative_in_the_other(
    db_session, api_client
):
    """May spent 100; June took back 30 more than it spent. The ledger nets
    June against May (70); the history counts June as nothing (100)."""
    services, budget, checking, _, group = await _world(db_session, api_client.test_user)
    shopping = await create_category(db_session, budget, group, "Shopping")
    await create_transaction(db_session, budget, checking, "-100", MAY, category=shopping)
    await create_transaction(db_session, budget, checking, "30", JUNE, category=shopping)

    history, ledger, total = await _both(db_session, services, budget, shopping)

    assert total == D("70")
    assert ledger.spent[WINDOW.complete.index(date(2026, 6, 1))] == D("-30")
    assert (history.average_spent, history.months_included) == (D("100.00"), 1)
