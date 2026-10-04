"""Late arrivals count in the import month (`txn_filters.LATE_ARRIVAL`).

An anchored budget's walks start at the import month B from YNAB's figures at
B−1. A row dated in B−1 that reached IGAB after the import — a straggler that
cleared late, or one typed in by hand — was in neither: it moved cash and
nothing else, so it came out of Ready to Assign instead of its envelope, and a
card charge read as uncovered debt. It now counts in B.

The budget here is hand-built the way an import leaves it: accounts marked
`from_import`, history stamped `created_via='ynab'`, anchor rows at B−1 = June,
so B = July. Every figure is in round numbers worked on paper.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import ImportAnchor, Transaction
from igab.domain.dates import budget_month
from igab.domain.import_identity import YNAB_ORIGIN
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.card_payment import ensure_payment_category
from igab.services.transaction_service import TransactionCreate

from .anchored_budget import build_anchored_budget
from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)
from .invariants import assert_card_reserve_identity

MAY, JUN, JUL, AUG = (date(2026, m, 1) for m in (5, 6, 7, 8))
D = Decimal


async def _imported(db_session):
    return await build_anchored_budget(db_session)


async def _enter(b, account, day: date, amount: str, category=None) -> Transaction:
    """A row typed in by hand after the import — `created_via='manual'`."""
    return await b.services.transactions.create(
        b.budget.id,
        TransactionCreate(
            account_id=account.id,
            date=day,
            amount=D(amount),
            category_id=category.id if category else None,
            cleared="cleared",
        ),
    )


async def _july(b):
    summary = await b.services.budgets.get_budget_summary(b.budget.id, JUL)
    by_cat = {c.category_id: c for c in summary.category_balances}
    return summary, by_cat


async def test_the_imported_history_stays_in_the_anchor(db_session):
    """The baseline every other test moves from: June's YNAB rows are inside
    the anchor, so July opens Groceries at 50 + 300 = 350, Dining at 100."""
    b = await _imported(db_session)
    summary, by_cat = await _july(b)
    assert by_cat[b.groceries.id].activity == D("0")
    assert by_cat[b.groceries.id].available == D("350")
    assert by_cat[b.dining.id].available == D("100")
    assert summary.late_arrivals == []


async def test_a_late_cash_row_counts_in_the_import_month(db_session):
    """A 40 grocery run dated June 28, typed in after the import: July's
    Groceries spends it (350 − 40 = 310) and Ready to Assign does not move.
    Before, Groceries stayed at 350 and Ready to Assign fell by 40."""
    b = await _imported(db_session)
    before, _ = await _july(b)
    await _enter(b, b.checking, date(2026, 6, 28), "-40.00", b.groceries)
    after, by_cat = await _july(b)
    assert by_cat[b.groceries.id].activity == D("-40")
    assert by_cat[b.groceries.id].available == D("310")
    assert after.to_be_assigned == before.to_be_assigned


async def test_a_synced_straggler_counts_the_same_as_a_typed_one(db_session):
    """Origin does not matter, only that it is not a YNAB row: a bank row
    (`created_via='sync'`) dated June 30 counts in July too."""
    b = await _imported(db_session)
    await create_transaction(
        db_session,
        b.budget,
        b.checking,
        "-25.00",
        date(2026, 6, 30),
        category=b.groceries,
        created_via="sync",
    )
    _, by_cat = await _july(b)
    assert by_cat[b.groceries.id].available == D("325")


async def test_an_older_straggler_stays_history(db_session):
    """Only the anchor month. A May row arriving now is history, exactly as
    every straggler was before: Groceries does not move, Ready to Assign
    takes it."""
    b = await _imported(db_session)
    before, _ = await _july(b)
    await _enter(b, b.checking, date(2026, 5, 20), "-40.00", b.groceries)
    after, by_cat = await _july(b)
    assert by_cat[b.groceries.id].available == D("350")
    assert after.to_be_assigned == before.to_be_assigned - D("40")


async def test_an_account_linked_after_the_import_keeps_its_history(db_session):
    """A newly linked account's bank history is opening position — its
    Starting Balance already nets it. Counting its June rows in July would
    charge Groceries for money the budget never had."""
    b = await _imported(db_session)
    savings = await create_account(db_session, b.budget, "New Savings")
    assert savings.from_import is False
    await _enter(b, savings, date(2026, 6, 28), "-40.00", b.groceries)
    _, by_cat = await _july(b)
    assert by_cat[b.groceries.id].available == D("350")


async def test_a_ynab_row_in_the_anchor_month_never_counts_twice(db_session):
    """A YNAB row dated June is in the anchor's 50 already. Adding another —
    the importer's own stamp — must not reach July."""
    b = await _imported(db_session)
    await create_transaction(
        db_session,
        b.budget,
        b.checking,
        "-40.00",
        date(2026, 6, 28),
        category=b.groceries,
        created_via=YNAB_ORIGIN,
    )
    _, by_cat = await _july(b)
    assert by_cat[b.groceries.id].available == D("350")


async def test_a_late_card_charge_is_covered_in_the_import_month(db_session):
    """A 60 Dining charge on the Visa dated June 29: July's Dining (100) pays
    for it, so 60 moves to the Visa's Set aside and nothing new rides. Before,
    the walk dropped it and the 60 read as uncovered debt."""
    b = await _imported(db_session)
    before, _ = await _july(b)
    visa_before = next(c for c in before.cards if c.name == "Visa")
    await _enter(b, b.visa, date(2026, 6, 29), "-60.00", b.dining)
    after, by_cat = await _july(b)
    visa = next(c for c in after.cards if c.name == "Visa")
    assert by_cat[b.dining.id].available == D("40")
    assert visa.set_aside == visa_before.set_aside + D("60")
    assert visa.uncovered == visa_before.uncovered == D("100")
    assert visa.reserve_discrepancy == D("0")
    await assert_card_reserve_identity(db_session, b.budget.id)


async def test_a_card_imported_in_credit_keeps_its_opening_credit(db_session):
    """A card that arrives holding 80 of credit (a June refund nobody filed),
    then a late 100 Groceries charge dated June 29. The opening credit is the
    card's balance at B−1 by the reserve's own bucket — still 80. Read by
    date, the late charge came off it and the card reported drift forever."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    amex = await create_account(db_session, budget, "Amex", account_type="credit_card")
    for account in (checking, amex):
        account.from_import = True
    await ensure_payment_category(db_session, amex)
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 6, 2), created_via=YNAB_ORIGIN
    )
    await create_transaction(
        db_session, budget, amex, "80.00", date(2026, 6, 5), created_via=YNAB_ORIGIN
    )
    db_session.add(
        ImportAnchor(
            budget_id=budget.id,
            month=JUN,
            kind="available",
            category_id=groceries.id,
            amount=D("0"),
        )
    )
    await db_session.flush()
    await services.budgets.set_assignment(budget.id, groceries.id, JUL, D("100"))
    await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=amex.id,
            date=date(2026, 6, 29),
            amount=D("-100.00"),
            category_id=groceries.id,
            cleared="cleared",
        ),
    )
    summary = await services.budgets.get_budget_summary(budget.id, JUL)
    card = next(c for c in summary.cards if c.name == "Amex")
    assert card.reserve_discrepancy == D("0")
    await assert_card_reserve_identity(db_session, budget.id)


async def test_the_register_says_which_month_a_row_counts_in(db_session):
    """Served on every row: the late one counts in July; a YNAB June row
    counts in June and predates the import; a July row is ordinary."""
    b = await _imported(db_session)
    late = await _enter(b, b.checking, date(2026, 6, 28), "-40.00", b.groceries)
    july = await _enter(b, b.checking, date(2026, 7, 3), "-10.00", b.groceries)
    repo = TransactionRepository(db_session)
    late_row = await repo.get(late.id)
    july_row = await repo.get(july.id)
    ynab_row = (
        await db_session.execute(
            repo.with_computed(
                select(Transaction).where(
                    Transaction.budget_id == b.budget.id, Transaction.created_via == YNAB_ORIGIN
                )
            ).limit(1)
        )
    ).scalar_one()
    assert (late_row.counts_in_month, late_row.predates_import) == (JUL, False)
    assert (july_row.counts_in_month, july_row.predates_import) == (JUL, False)
    assert (ynab_row.counts_in_month, ynab_row.predates_import) == (JUN, True)


async def test_an_unanchored_budget_counts_every_row_in_its_own_month(db_session):
    """No anchor, no rule: `from_import` and the origin change nothing, and
    nothing predates anything."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    checking.from_import = True
    row = await create_transaction(
        db_session, budget, checking, "-40.00", date(2026, 6, 28), created_via="manual"
    )
    loaded = await TransactionRepository(db_session).get(row.id)
    assert (loaded.counts_in_month, loaded.predates_import) == (JUN, False)
    summary = await services.budgets.get_budget_summary(budget.id, JUL)
    assert summary.late_arrivals == []


async def test_the_import_month_lists_its_late_arrivals(db_session):
    """July names the row that moved Groceries; August, which is not the
    import month, lists nothing."""
    b = await _imported(db_session)
    late = await _enter(b, b.checking, date(2026, 6, 28), "-40.00", b.groceries)
    july, _ = await _july(b)
    assert [a.transaction_id for a in july.late_arrivals] == [late.id]
    (arrival,) = july.late_arrivals
    assert (arrival.amount, arrival.category_id) == (D("-40"), b.groceries.id)
    august = await b.services.budgets.get_budget_summary(b.budget.id, AUG)
    assert august.late_arrivals == []


async def test_spending_reports_keep_the_real_date(db_session):
    """The deliberate divergence, pinned: the spending report answers *when*
    money was spent, so the late row stays in June there while the envelope
    counts it in July."""
    b = await _imported(db_session)
    await _enter(b, b.checking, date(2026, 6, 28), "-40.00", b.groceries)
    rows = await TransactionRepository(db_session).spending_by_month(
        b.budget.id, MAY, date(2026, 7, 31)
    )
    by_month = {}
    for month, total, _sinking in rows:
        key = month.date() if hasattr(month, "date") else month
        by_month[key] = by_month.get(key, D("0")) + D(str(total))
    assert by_month.get(JUL, D("0")) == D("0")
    assert by_month[JUN] < D("0")


async def test_the_savings_cut_and_plan_ledger_follow_the_bucket(db_session):
    """Readers of the envelope's months read its bucket. A mid-June savings
    cut takes nothing for the late row (June's Available never held it); the
    plan ledger pairs it with July's assignment."""
    from igab.services.plan_ledger import plan_ledger

    b = await _imported(db_session)
    await _enter(b, b.checking, date(2026, 6, 28), "-40.00", b.groceries)
    repo = TransactionRepository(db_session)
    cut = await repo.sum_categories_dated_after(
        b.budget.id, [b.groceries.id], date(2026, 6, 15), date(2026, 6, 30)
    )
    assert cut.get(b.groceries.id, D("0")) == D("0")
    ledger = await plan_ledger(db_session, b.budget.id, JUL, date(2026, 7, 31))
    july = ledger[b.groceries.id].months[JUL]
    assert july.assigned == D("300")
    assert july.spent == D("40")


# ── The pure twin agrees with the SQL ────────────────────────────────────────

CASES = [
    # (origin, from_import, day) → the month the row should count in
    ("manual", True, date(2026, 6, 28)),
    ("sync", True, date(2026, 6, 1)),
    ("import", True, date(2026, 6, 15)),  # a CSV file run after the import
    (YNAB_ORIGIN, True, date(2026, 6, 28)),
    (None, True, date(2026, 6, 28)),
    ("manual", False, date(2026, 6, 28)),
    ("manual", True, date(2026, 5, 31)),
    ("manual", True, date(2026, 7, 1)),
    ("manual", True, date(2026, 8, 9)),
]


@pytest.mark.parametrize(("origin", "from_import", "day"), CASES)
async def test_the_pure_twin_agrees_with_the_sql(db_session, origin, from_import, day):
    """`domain.dates.budget_month` is the walk's copy of `BUDGET_MONTH` for the
    layers that run no SQL. Irreducible duplication, held together here over
    every clause of the rule rather than by a comment."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    account = await create_account(db_session, budget, "Checking")
    account.from_import = from_import
    db_session.add(
        ImportAnchor(
            budget_id=budget.id,
            month=JUN,
            kind="uncovered",
            account_id=account.id,
            amount=D("1"),
        )
    )
    await db_session.flush()
    row = await create_transaction(db_session, budget, account, "-1.00", day, created_via=origin)
    served = (await TransactionRepository(db_session).get(row.id)).counts_in_month
    pure = budget_month(
        day,
        anchor_month=JUN,
        late_eligible=(origin or YNAB_ORIGIN) != YNAB_ORIGIN and from_import,
    )
    assert served == pure
    del services
