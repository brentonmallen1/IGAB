"""Several budget moves as one write record exactly what one move at a time did.

The dropdown's Apply and Cover Overspending used to call `move_money` once
per envelope: an audit row with its own flush, a get-or-create, an update and
a reselect for each side. `move_money_many` writes the month once. What it
must not change is the record — the audit rows, the change rows and their
before/after figures — because per-move undo (`undo_move`), the batch undo's
move groups (`_move_groups`) and redo all read those rows back.

So the oracle here is the old way, run on an identical budget: the same moves
through `move_money` one at a time, inside one batch as Apply ran them.
Moves through the same envelope twice are in the list on purpose — the bulk
write lands once, and the change rows still have to chain.
"""

from datetime import date
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from igab.db.models import BudgetAssignment, BudgetMove, ChangeLog
from igab.domain.exceptions import InvariantViolation
from igab.services.budget_service import MoneyMove
from igab.services.undo_service import UndoService

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)
from .invariants import assert_financial_invariants

MONTH = date(2026, 7, 1)


async def _budget(db_session):
    services = make_services(db_session)
    budget = await create_budget(db_session, await create_user(db_session))
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    inflow = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    cats = {"Inflow": inflow}
    for name in ("Groceries", "Dining", "Fuel"):
        cats[name] = await create_category(db_session, budget, everyday, name)
    await create_transaction(db_session, budget, checking, "1000.00", MONTH, category=inflow)
    await services.budgets.set_assignment(budget.id, cats["Groceries"].id, MONTH, D("600"))
    await services.budgets.set_assignment(budget.id, cats["Dining"].id, MONTH, D("100"))
    await db_session.flush()
    return services, budget, cats


#: (from, to, amount) by name; None is Ready to Assign. Groceries and Dining
#: each appear in two moves; Fuel has no row until the last one makes it.
MOVES = [
    (None, "Groceries", "40"),
    ("Dining", None, "30"),
    ("Groceries", "Dining", "15"),
    (None, "Fuel", "12.50"),
]


def _moves(cats) -> list[MoneyMove]:
    return [
        MoneyMove(
            cats[src].id if src else None,
            cats[dst].id if dst else None,
            D(amount),
        )
        for src, dst, amount in MOVES
    ]


async def _record(db_session, budget, cats):
    """What the budget holds and what was written about it, by name."""
    name = {c.id: n for n, c in cats.items()}
    assigned = {
        name[cid]: amount
        for cid, amount in (
            await db_session.execute(
                select(BudgetAssignment.category_id, BudgetAssignment.assigned).where(
                    BudgetAssignment.budget_id == budget.id
                )
            )
        ).all()
    }
    moves = [
        (name.get(m.from_category_id), name.get(m.to_category_id), m.amount)
        for m in (
            await db_session.execute(
                select(BudgetMove)
                .where(BudgetMove.budget_id == budget.id)
                .order_by(BudgetMove.amount)
            )
        ).scalars()
    ]
    changes = (
        (
            await db_session.execute(
                select(ChangeLog)
                .where(ChangeLog.budget_id == budget.id, ChangeLog.entity_type == "assignment")
                .order_by(ChangeLog.seq)
            )
        )
        .scalars()
        .all()
    )
    move_amount = {
        str(m.id): m.amount
        for m in (
            await db_session.execute(select(BudgetMove).where(BudgetMove.budget_id == budget.id))
        ).scalars()
    }
    rows = [
        (
            c.before["assigned"],
            c.after["assigned"],
            # Which move the row belongs to, by the move's amount (unique here).
            move_amount.get(c.after.get("_move_id", "")),
        )
        for c in changes
    ]
    batches = {c.batch_id for c in changes if c.after.get("_move_id")}
    return assigned, moves, rows, len(batches)


async def test_bulk_moves_record_what_one_move_at_a_time_recorded(db_session):
    one_services, one_budget, one_cats = await _budget(db_session)
    with one_services.budgets.changes.batch():
        for move in _moves(one_cats):
            await one_services.budgets.move_money(
                one_budget.id, move.from_category_id, move.to_category_id, move.amount, MONTH
            )
    bulk_services, bulk_budget, bulk_cats = await _budget(db_session)
    with bulk_services.budgets.changes.batch():
        await bulk_services.budgets.move_money_many(bulk_budget.id, MONTH, _moves(bulk_cats))
    await db_session.flush()

    one = await _record(db_session, one_budget, one_cats)
    bulk = await _record(db_session, bulk_budget, bulk_cats)

    assert bulk == one
    # And the figures are the ones the moves describe, by hand.
    assert bulk[0] == {"Groceries": D("625"), "Dining": D("85"), "Fuel": D("12.50")}
    assert bulk[3] == 1, "every move in one undo batch"
    await assert_financial_invariants(db_session, bulk_budget.id)


async def test_undoing_the_batch_walks_the_chained_rows_back(db_session):
    services, budget, cats = await _budget(db_session)
    before, *_ = await _record(db_session, budget, cats)
    with services.budgets.changes.batch() as batch_id:
        await services.budgets.move_money_many(budget.id, MONTH, _moves(cats))
    await db_session.flush()

    result = await UndoService(db_session).undo_batch(budget.id, batch_id)

    assert result.skipped == []
    after, moves, *_ = await _record(db_session, budget, cats)
    assert {k: v for k, v in after.items() if v} == before
    assert moves == [], "undoing a move drops its audit row"


@pytest.mark.parametrize("bad", ["Inflow", "archived"])
async def test_one_refused_envelope_refuses_every_move_and_writes_nothing(db_session, bad):
    services, budget, cats = await _budget(db_session)
    if bad == "archived":
        cats["Fuel"].is_archived = True
        await db_session.flush()
    target = cats["Inflow"] if bad == "Inflow" else cats["Fuel"]
    before = await _record(db_session, budget, cats)

    with pytest.raises(InvariantViolation):
        await services.budgets.move_money_many(
            budget.id,
            MONTH,
            [MoneyMove(None, cats["Groceries"].id, D("10")), MoneyMove(None, target.id, D("5"))],
        )

    await db_session.flush()
    assert await _record(db_session, budget, cats) == before


async def test_no_moves_is_no_write(db_session):
    services, budget, cats = await _budget(db_session)
    before = await _record(db_session, budget, cats)
    await services.budgets.move_money_many(budget.id, MONTH, [])
    assert await _record(db_session, budget, cats) == before
