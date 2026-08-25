"""Undoing a real category delete.

The delete records **one** change row carrying `_`-prefixed bookkeeping, not a
change row per affected transaction — see `CategoryService._record_delete` for
why. These tests hold that row to the same standard as any other undo: it puts
everything back, it leaves alone anything the user touched in the meantime, and
it refuses to run twice.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import BudgetAssignment, ChangeLog
from igab.domain.exceptions import UndoConflict
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository
from igab.services.category_service import CategoryService
from igab.services.undo_service import UndoService

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_payee,
    create_scheduled_transaction,
    create_transaction,
    create_user,
    make_services,
)

AUG = date(2026, 8, 1)
SEP = date(2026, 9, 1)


def _service(db_session, services) -> CategoryService:
    return CategoryService(
        db_session,
        CategoryRepository(db_session),
        CategoryGroupRepository(db_session),
        services.budgets,
    )


async def _setup(db_session):
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Everyday")
    account = await create_account(db_session, budget, "Checking")
    groceries = await create_category(db_session, budget, group, "Groceries")
    other = await create_category(db_session, budget, group, "Other")

    await create_transaction(db_session, budget, account, "1000", AUG)
    await create_budget_assignment(db_session, budget, groceries, AUG, "100")
    await create_budget_assignment(db_session, budget, groceries, SEP, "50")
    spends = [
        await create_transaction(
            db_session, budget, account, "-10", date(2026, 8, day), category=groceries
        )
        for day in (10, 11, 12)
    ]
    await db_session.flush()
    return budget, group, account, groceries, other, spends


# ─── One row, not hundreds ────────────────────────────────────────────────────


async def test_delete_records_exactly_one_change_row(db_session):
    """A change row per transaction would page the Activity view into
    "Batch of 50" for twenty screens, and `undo_batch`'s per-row staleness
    check would make one later edit poison the whole delete."""
    services = make_services(db_session)
    budget, _, _, groceries, _, _ = await _setup(db_session)

    await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.flush()

    rows = list(
        (await db_session.execute(select(ChangeLog).where(ChangeLog.budget_id == budget.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].entity_type == "category"
    assert rows[0].action == "delete"
    assert rows[0].batch_id is None


# ─── Full restore ─────────────────────────────────────────────────────────────


async def test_undo_restores_everything(db_session):
    services = make_services(db_session)
    budget, _, account, groceries, _, spends = await _setup(db_session)
    payee = await create_payee(db_session, budget, "Corner Store")
    payee.default_category_id = groceries.id
    sched = await create_scheduled_transaction(db_session, budget, account, "-25", "monthly", AUG)
    sched.category_id = groceries.id
    await db_session.flush()

    tba_before = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned

    result = await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.flush()

    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()

    await db_session.refresh(groceries)
    assert groceries.is_deleted is False
    assert groceries.name == "Groceries"

    for spend in spends:
        await db_session.refresh(spend)
        assert spend.category_id == groceries.id
        assert spend.prior_category_id is None
        assert spend.prior_category_name is None

    assignments = sorted(
        (
            (
                await db_session.execute(
                    select(BudgetAssignment).where(BudgetAssignment.category_id == groceries.id)
                )
            )
            .scalars()
            .all()
        ),
        key=lambda a: a.month,
    )
    assert [(a.month, a.assigned) for a in assignments] == [
        (AUG, Decimal("100.0000")),
        (SEP, Decimal("50.0000")),
    ]

    await db_session.refresh(payee)
    await db_session.refresh(sched)
    assert payee.default_category_id == groceries.id
    assert sched.category_id == groceries.id

    tba_after = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned
    assert tba_after == tba_before, "undo must return Ready to Assign to where it was"


async def test_undo_restores_a_move(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, other, spends = await _setup(db_session)

    result = await _service(db_session, services).delete_categories(
        budget.id, [groceries.id], move_to=other.id, month=AUG
    )
    await db_session.flush()
    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()

    for spend in spends:
        await db_session.refresh(spend)
        assert spend.category_id == groceries.id
        assert spend.prior_category_id is None


async def test_undo_does_not_drag_back_rows_that_were_already_in_the_target(db_session):
    """Provenance, not "everything in the destination", is what undo moves —
    otherwise restoring Groceries would empty Other of its own history."""
    services = make_services(db_session)
    budget, group, account, groceries, other, _ = await _setup(db_session)
    native = await create_transaction(
        db_session, budget, account, "-5", date(2026, 8, 20), category=other
    )
    await db_session.flush()

    result = await _service(db_session, services).delete_categories(
        budget.id, [groceries.id], move_to=other.id, month=AUG
    )
    await db_session.flush()
    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()

    await db_session.refresh(native)
    assert native.category_id == other.id


# ─── What the user touched in between stays touched ───────────────────────────


async def test_refiled_rows_stay_where_the_user_put_them(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, other, spends = await _setup(db_session)

    result = await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.flush()

    # The user files one of the orphans somewhere else before undoing.
    refiled = spends[0]
    refiled.category_id = other.id
    await db_session.flush()

    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()

    await db_session.refresh(refiled)
    assert refiled.category_id == other.id, "undo overwrote a deliberate re-file"
    assert refiled.prior_category_id == groceries.id

    for spend in spends[1:]:
        await db_session.refresh(spend)
        assert spend.category_id == groceries.id


async def test_a_payee_default_set_in_the_meantime_survives(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, other, _ = await _setup(db_session)
    payee = await create_payee(db_session, budget, "Corner Store")
    payee.default_category_id = groceries.id
    await db_session.flush()

    result = await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.flush()

    payee.default_category_id = other.id
    await db_session.flush()

    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()

    await db_session.refresh(payee)
    assert payee.default_category_id == other.id


async def test_reconciled_rows_come_back_without_tripping_the_guard(db_session):
    """`_undo_update` refuses reconciled transactions and `force` does not
    override it — deliberately, and pinned by its own tests. This path is a
    bulk update on a `category` entity, so that guard is never consulted, the
    same footing `_undo_merge` re-points payees on."""
    services = make_services(db_session)
    budget, _, account, groceries, _, _ = await _setup(db_session)
    locked = await create_transaction(
        db_session,
        budget,
        account,
        "-7",
        date(2026, 8, 14),
        category=groceries,
        cleared="reconciled",
    )
    await db_session.flush()

    result = await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.flush()
    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()

    await db_session.refresh(locked)
    assert locked.category_id == groceries.id
    assert locked.cleared == "reconciled"


# ─── Groups ───────────────────────────────────────────────────────────────────


async def test_undo_of_a_group_delete_restores_group_and_categories(db_session):
    services = make_services(db_session)
    budget, group, _, groceries, other, spends = await _setup(db_session)

    result = await _service(db_session, services).delete_group(budget.id, group.id, month=AUG)
    await db_session.flush()
    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()

    await db_session.refresh(group)
    await db_session.refresh(groceries)
    await db_session.refresh(other)
    assert group.is_deleted is False
    assert groceries.is_deleted is False
    assert other.is_deleted is False

    for spend in spends:
        await db_session.refresh(spend)
        assert spend.category_id == groceries.id


# ─── Conflicts ────────────────────────────────────────────────────────────────


async def test_double_undo_conflicts(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, _, _ = await _setup(db_session)

    result = await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.flush()
    undo = UndoService(db_session)
    await undo.undo_change(budget.id, result.change_id)
    await db_session.flush()

    with pytest.raises(UndoConflict, match="already been undone"):
        await undo.undo_change(budget.id, result.change_id)


async def test_undo_conflicts_when_the_category_was_restored_by_hand(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, _, _ = await _setup(db_session)

    result = await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.flush()

    groceries.is_deleted = False
    await db_session.flush()

    with pytest.raises(UndoConflict, match="no longer deleted"):
        await UndoService(db_session).undo_change(budget.id, result.change_id)


async def test_undo_restores_a_link_that_is_still_free(db_session):
    """Restoring a category cannot start a fight over an account or liability
    — see `test_a_deleted_category_never_holds_a_link` for why — so the only
    link an undo can put back is one that was already null. This pins that the
    restore leaves the binding columns alone rather than inventing a claim."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Debt")
    card = await create_account(db_session, budget, "Visa", account_type="credit_card")
    payment = await create_category(db_session, budget, group, "Visa Payment")
    payment.linked_account_id = card.id
    await db_session.flush()

    # The account goes first, which clears the link — the only route by which
    # this category becomes deletable at all.
    await services.account_repo.soft_delete(card.id)
    result = await _service(db_session, services).delete_categories(budget.id, [payment.id], month=AUG)
    await db_session.flush()

    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()

    await db_session.refresh(payment)
    assert payment.is_deleted is False
    assert payment.linked_account_id is None
