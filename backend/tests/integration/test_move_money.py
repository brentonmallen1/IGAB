"""Move money between envelopes — the core daily YNAB action. A null side
means To-Be-Assigned; every move is conserved (TBA + Σ available constant)
and recorded in the audit trail."""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.exceptions import InvariantViolation

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_transaction,
    create_user,
    make_services,
)

MONTH = date(2026, 7, 1)


async def _setup(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Checking")
    income_group = await create_category_group(db_session, budget, "Income", is_system=True)
    income_cat = await create_category(db_session, budget, income_group, "Inflow")
    everyday = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, everyday, "Groceries")
    dining = await create_category(db_session, budget, everyday, "Dining")
    await create_transaction(
        db_session, budget, checking, "1000.00", date(2026, 7, 2), category=income_cat
    )
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("600.00"))
    await services.budgets.set_assignment(budget.id, dining.id, MONTH, Decimal("100.00"))
    return services, budget, groceries, dining


async def _snapshot(services, budget):
    summary = await services.budgets.get_budget_summary(budget.id, MONTH)
    return summary, {b.category_id: b for b in summary.category_balances}


async def test_move_between_categories_conserves_tba(db_session):
    services, budget, groceries, dining = await _setup(db_session)

    await services.budgets.move_money(budget.id, groceries.id, dining.id, Decimal("150.00"), MONTH)

    summary, by_cat = await _snapshot(services, budget)
    assert by_cat[groceries.id].available == Decimal("450.00")
    assert by_cat[dining.id].available == Decimal("250.00")
    assert summary.to_be_assigned == Decimal("300.00"), "TBA untouched by envelope moves"


async def test_move_from_tba_to_category(db_session):
    services, budget, groceries, dining = await _setup(db_session)

    await services.budgets.move_money(budget.id, None, dining.id, Decimal("200.00"), MONTH)

    summary, by_cat = await _snapshot(services, budget)
    assert by_cat[dining.id].available == Decimal("300.00")
    assert summary.to_be_assigned == Decimal("100.00")


async def test_move_from_category_back_to_tba(db_session):
    services, budget, groceries, dining = await _setup(db_session)

    await services.budgets.move_money(budget.id, groceries.id, None, Decimal("600.00"), MONTH)

    summary, by_cat = await _snapshot(services, budget)
    assert by_cat[groceries.id].available == Decimal("0")
    assert summary.to_be_assigned == Decimal("900.00")


async def test_cover_overspending_flow(db_session):
    """The daily action: dining overspends, cover it from groceries."""
    services, budget, groceries, dining = await _setup(db_session)
    accounts = {a.name: a for a in await services.account_repo.get_all(budget.id)}
    await create_transaction(
        db_session, budget, accounts["Checking"], "-160.00", date(2026, 7, 10), category=dining
    )

    _, by_cat = await _snapshot(services, budget)
    assert by_cat[dining.id].available == Decimal("-60.00")

    await services.budgets.move_money(budget.id, groceries.id, dining.id, Decimal("60.00"), MONTH)

    summary, by_cat = await _snapshot(services, budget)
    assert by_cat[dining.id].available == Decimal("0")
    assert by_cat[groceries.id].available == Decimal("540.00")
    assert summary.to_be_assigned == Decimal("300.00")


async def test_validation_rejections(db_session):
    services, budget, groceries, dining = await _setup(db_session)

    with pytest.raises(InvariantViolation, match="positive"):
        await services.budgets.move_money(budget.id, groceries.id, dining.id, Decimal("0"), MONTH)
    with pytest.raises(InvariantViolation, match="positive"):
        await services.budgets.move_money(
            budget.id, groceries.id, dining.id, Decimal("-5.00"), MONTH
        )
    with pytest.raises(InvariantViolation, match="different"):
        await services.budgets.move_money(
            budget.id, groceries.id, groceries.id, Decimal("10.00"), MONTH
        )
    with pytest.raises(InvariantViolation, match="different"):
        await services.budgets.move_money(budget.id, None, None, Decimal("10.00"), MONTH)

    # Foreign-budget category must be rejected
    other_user = await create_user(db_session)
    other_budget = await create_budget(db_session, other_user)
    other_group = await create_category_group(db_session, other_budget, "G")
    foreign_cat = await create_category(db_session, other_budget, other_group, "Foreign")
    with pytest.raises(InvariantViolation, match="belong"):
        await services.budgets.move_money(
            budget.id, groceries.id, foreign_cat.id, Decimal("10.00"), MONTH
        )


async def test_move_history_recorded(db_session):
    services, budget, groceries, dining = await _setup(db_session)

    await services.budgets.move_money(budget.id, groceries.id, dining.id, Decimal("25.00"), MONTH)
    await services.budgets.move_money(budget.id, None, groceries.id, Decimal("50.00"), MONTH)

    moves = await services.budgets.get_move_history(budget.id, MONTH)
    assert len(moves) == 2
    # Both moves share one transaction timestamp (server now()), so match by
    # content rather than order.
    tba_move = next(m for m in moves if m.from_category_id is None)
    assert tba_move.to_category_id == groceries.id
    assert tba_move.amount == Decimal("50.00")
    envelope_move = next(m for m in moves if m.from_category_id == groceries.id)
    assert envelope_move.to_category_id == dining.id
    assert envelope_move.amount == Decimal("25.00")


async def test_move_money_api(api_client, db_session):
    services = make_services(db_session)
    budget = await create_budget(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    dining = await create_category(db_session, budget, group, "Dining")
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("100.00"))

    resp = await api_client.post(
        f"/api/v1/{budget.id}/budget/move-money",
        json={
            "from_category_id": str(groceries.id),
            "to_category_id": str(dining.id),
            "amount": "40.00",
            "month": "2026-07-01",
        },
    )
    assert resp.status_code == 204

    resp = await api_client.get(f"/api/v1/{budget.id}/budget/moves", params={"month": "2026-07-01"})
    assert resp.status_code == 200
    moves = resp.json()
    assert len(moves) == 1
    assert Decimal(moves[0]["amount"]) == Decimal("40.00")

    # Money validation applies here too
    resp = await api_client.post(
        f"/api/v1/{budget.id}/budget/move-money",
        json={
            "from_category_id": str(groceries.id),
            "to_category_id": str(dining.id),
            "amount": "NaN",
            "month": "2026-07-01",
        },
    )
    assert resp.status_code == 422


async def test_undo_move_reverses_only_that_move_and_drops_its_row(db_session):
    from igab.services.undo_service import UndoService

    services, budget, groceries, dining = await _setup(db_session)
    await services.budgets.move_money(budget.id, groceries.id, dining.id, Decimal("25.00"), MONTH)
    # A later move through the same category must survive the undo of the first
    await services.budgets.move_money(budget.id, None, dining.id, Decimal("10.00"), MONTH)
    moves = await services.budgets.get_move_history(budget.id, MONTH)
    first = next(m for m in moves if m.from_category_id == groceries.id)

    undone = await UndoService(db_session).undo_move(budget.id, first.id)
    assert len(undone) == 2, "both sides of the move are stamped undone"

    _, bal = await _snapshot(services, budget)
    assert bal[groceries.id].assigned == Decimal("600.00")
    assert bal[dining.id].assigned == Decimal("110.00"), "the later $10 move is kept"
    moves = await services.budgets.get_move_history(budget.id, MONTH)
    assert [m.amount for m in moves] == [Decimal("10.00")], "the undone move left the list"

    # A second undo of the same move finds nothing pending and nothing to drop
    with pytest.raises(Exception):
        await UndoService(db_session).undo_move(budget.id, first.id)


async def test_undo_move_after_log_undo_only_drops_the_row(db_session):
    from igab.services.undo_service import UndoService

    services, budget, groceries, dining = await _setup(db_session)
    await services.budgets.move_money(budget.id, groceries.id, dining.id, Decimal("25.00"), MONTH)
    move = (await services.budgets.get_move_history(budget.id, MONTH))[0]
    undo = UndoService(db_session)
    rows = await undo.repo.get_for_move(budget.id, move.id)
    await undo.undo_batch(budget.id, rows[0].batch_id)
    # The batch undo already dropped the audit row; a stale row (from before
    # moves were linked to their changes) would still be listed — undo_move
    # on it must reverse nothing and just remove it.
    db_session.add(
        type(move)(
            id=move.id,
            budget_id=budget.id,
            month=MONTH,
            from_category_id=groceries.id,
            to_category_id=dining.id,
            amount=Decimal("25.00"),
        )
    )
    await db_session.flush()
    assert await undo.undo_move(budget.id, move.id) == []
    assert await services.budgets.get_move_history(budget.id, MONTH) == []
    _, bal = await _snapshot(services, budget)
    assert bal[groceries.id].assigned == Decimal("600.00"), "money was not reversed twice"


async def test_undo_move_refuses_a_move_with_no_linked_rows(db_session):
    from igab.domain.exceptions import UndoConflict
    from igab.services.undo_service import UndoService

    services, budget, groceries, dining = await _setup(db_session)
    # A row from before moves carried their change ids: nothing links back
    legacy = services.budgets.move_repo.model(
        budget_id=budget.id,
        month=MONTH,
        from_category_id=groceries.id,
        to_category_id=dining.id,
        amount=Decimal("5.00"),
    )
    db_session.add(legacy)
    await db_session.flush()
    with pytest.raises(UndoConflict):
        await UndoService(db_session).undo_move(budget.id, legacy.id)
    assert len(await services.budgets.get_move_history(budget.id, MONTH)) == 1, "still listed"


async def test_undo_of_a_bulk_batch_drops_its_moves(db_session):
    from igab.services.undo_service import UndoService

    services, budget, groceries, dining = await _setup(db_session)
    with services.budgets.changes.batch() as batch_id:
        await services.budgets.move_money(budget.id, None, groceries.id, Decimal("5.00"), MONTH)
        await services.budgets.move_money(budget.id, None, dining.id, Decimal("7.00"), MONTH)
    assert len(await services.budgets.get_move_history(budget.id, MONTH)) == 2

    await UndoService(db_session).undo_batch(budget.id, batch_id)

    assert await services.budgets.get_move_history(budget.id, MONTH) == []
    _, bal = await _snapshot(services, budget)
    assert bal[groceries.id].assigned == Decimal("600.00")
    assert bal[dining.id].assigned == Decimal("100.00")


async def test_redo_restores_the_move_and_its_row(db_session):
    from igab.domain.exceptions import UndoConflict
    from igab.services.undo_service import UndoService

    services, budget, groceries, dining = await _setup(db_session)
    await services.budgets.move_money(budget.id, groceries.id, dining.id, Decimal("25.00"), MONTH)
    move = (await services.budgets.get_move_history(budget.id, MONTH))[0]
    undo = UndoService(db_session)
    await undo.undo_move(budget.id, move.id)
    assert await services.budgets.get_move_history(budget.id, MONTH) == []

    redone = await undo.redo_latest(budget.id)
    assert len(redone) == 2
    _, bal = await _snapshot(services, budget)
    assert bal[groceries.id].assigned == Decimal("575.00")
    assert bal[dining.id].assigned == Decimal("125.00")
    moves = await services.budgets.get_move_history(budget.id, MONTH)
    assert [m.id for m in moves] == [move.id], "the audit row is back under its original id"

    # Undo again, then do something new: the redo stack is gone
    await undo.undo_move(budget.id, move.id)
    await services.budgets.move_money(budget.id, None, dining.id, Decimal("1.00"), MONTH)
    with pytest.raises(UndoConflict):
        await undo.redo_latest(budget.id)


async def test_undo_move_api(api_client, db_session):
    services = make_services(db_session)
    budget = await create_budget(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget, "Everyday")
    groceries = await create_category(db_session, budget, group, "Groceries")
    dining = await create_category(db_session, budget, group, "Dining")
    await services.budgets.set_assignment(budget.id, groceries.id, MONTH, Decimal("100.00"))
    await services.budgets.move_money(budget.id, groceries.id, dining.id, Decimal("40.00"), MONTH)
    move = (await services.budgets.get_move_history(budget.id, MONTH))[0]

    resp = await api_client.post(f"/api/v1/{budget.id}/budget/moves/{move.id}/undo")
    assert resp.status_code == 200
    assert len(resp.json()["undone_change_ids"]) == 2
    resp = await api_client.get(f"/api/v1/{budget.id}/budget/moves", params={"month": "2026-07-01"})
    assert resp.json() == []

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/redo")
    assert resp.status_code == 200
    resp = await api_client.get(f"/api/v1/{budget.id}/budget/moves", params={"month": "2026-07-01"})
    assert len(resp.json()) == 1
