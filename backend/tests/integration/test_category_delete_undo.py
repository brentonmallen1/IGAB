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

from igab.db.models import (
    BudgetAssignment,
    BudgetView,
    BudgetViewPlacement,
    Category,
    ChangeLog,
)
from igab.domain.exceptions import UndoConflict
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.transaction_repo import TransactionRepository
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
        TransactionRepository(db_session),
        BudgetAssignmentRepository(db_session),
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

    # Re-queried, not refreshed: this category was hard-deleted (nothing
    # referenced it), so undo rebuilt the row from the change record rather
    # than clearing a flag on the one this test was holding.
    db_session.expunge_all()
    restored = await db_session.get(Category, payment.id)
    assert restored is not None, "undo must bring back a hard-deleted category"
    assert restored.is_deleted is False
    assert restored.linked_account_id is None


# ─── Review regressions: undo puts everything back where it was ──────────────


async def test_group_undo_restores_each_payee_default_to_its_own_category(db_session):
    """Measured before the fix: undoing a group delete filed EVERY payee
    default and scheduled transaction into the first category — Chipotle's
    default came back as Groceries. The bookkeeping is a mapping now."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Food")
    account = await create_account(db_session, budget, "Checking")
    groceries = await create_category(db_session, budget, group, "Groceries")
    dining = await create_category(db_session, budget, group, "Dining")
    groceries.sort_order = 0
    dining.sort_order = 1

    store = await create_payee(db_session, budget, "Corner Store")
    store.default_category_id = groceries.id
    chipotle = await create_payee(db_session, budget, "Chipotle")
    chipotle.default_category_id = dining.id
    sched = await create_scheduled_transaction(db_session, budget, account, "-25", "monthly", AUG)
    sched.category_id = dining.id
    await db_session.flush()

    result = await _service(db_session, services).delete_group(budget.id, group.id, month=AUG)
    await db_session.flush()
    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()

    await db_session.refresh(store)
    await db_session.refresh(chipotle)
    await db_session.refresh(sched)
    assert store.default_category_id == groceries.id
    assert chipotle.default_category_id == dining.id
    assert sched.category_id == dining.id


async def test_chained_delete_then_reverse_undo_returns_rows_home(db_session):
    """Measured before the fix: delete A into B, delete B, undo both in
    reverse — the rows stayed in B, because B's delete overwrote the
    provenance undo keyed on. Undo restores from the recorded id list now;
    provenance is display only."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Everyday")
    account = await create_account(db_session, budget, "Checking")
    a = await create_category(db_session, budget, group, "A")
    b = await create_category(db_session, budget, group, "B")
    txn = await create_transaction(db_session, budget, account, "-10", AUG, category=a)
    await db_session.flush()

    svc = _service(db_session, services)
    res_a = await svc.delete_categories(budget.id, [a.id], move_to=b.id, month=AUG)
    await db_session.flush()
    res_b = await svc.delete_categories(budget.id, [b.id], month=AUG)
    await db_session.flush()

    undo = UndoService(db_session)
    await undo.undo_change(budget.id, res_b.change_id)
    await db_session.flush()
    await undo.undo_change(budget.id, res_a.change_id)
    await db_session.flush()

    await db_session.refresh(txn)
    await db_session.refresh(a)
    await db_session.refresh(b)
    assert a.is_deleted is False and b.is_deleted is False
    assert txn.category_id == a.id, "reverse-order undo walks all the way home"
    assert txn.prior_category_id is None and txn.prior_category_name is None


async def test_out_of_order_undo_restores_the_category_but_not_rows_it_lost(db_session):
    """Undo A while B (which took A's rows and was then deleted itself) is
    still deleted: A comes back, but its rows are wherever B's delete put
    them — not at A's recorded destination, so the still-where-we-left-them
    rule leaves them. LIFO is the accurate direction; this pins what the
    other order does instead of leaving it to chance."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Everyday")
    account = await create_account(db_session, budget, "Checking")
    a = await create_category(db_session, budget, group, "A")
    b = await create_category(db_session, budget, group, "B")
    txn = await create_transaction(db_session, budget, account, "-10", AUG, category=a)
    await db_session.flush()

    svc = _service(db_session, services)
    res_a = await svc.delete_categories(budget.id, [a.id], move_to=b.id, month=AUG)
    await db_session.flush()
    res_b = await svc.delete_categories(budget.id, [b.id], month=AUG)
    await db_session.flush()

    undo = UndoService(db_session)
    await undo.undo_change(budget.id, res_a.change_id)
    await db_session.flush()

    await db_session.refresh(txn)
    await db_session.refresh(a)
    assert a.is_deleted is False
    assert txn.category_id is None, "the row is where B's delete left it"

    await undo.undo_change(budget.id, res_b.change_id)
    await db_session.flush()
    await db_session.refresh(txn)
    assert txn.category_id == b.id


async def test_undo_returns_the_cover_it_granted(db_session):
    """A move-delete grants the destination cover for the spending it
    absorbs; undo takes back exactly those deltas — an assignment the user
    edited in between keeps the edit and loses only the cover."""
    services = make_services(db_session)
    budget, _, account, groceries, other, _ = await _setup(db_session)

    b_aug_before = Decimal("0")
    result = await _service(db_session, services).delete_categories(
        budget.id, [groceries.id], move_to=other.id, month=AUG
    )
    await db_session.flush()

    def _assign_rows():
        return db_session.execute(
            select(BudgetAssignment).where(BudgetAssignment.category_id == other.id)
        )

    rows = {a.month: a for a in (await _assign_rows()).scalars().all()}
    assert rows[AUG].assigned == Decimal("30.0000"), "cover for the three -10 spends"

    # The user tops the destination up before changing their mind.
    rows[AUG].assigned = rows[AUG].assigned + Decimal("5")
    await db_session.flush()

    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()
    db_session.expunge_all()

    rows = {a.month: a for a in (await _assign_rows()).scalars().all()}
    assert rows[AUG].assigned == b_aug_before + Decimal("5"), (
        "the edit survives; only the cover comes back out"
    )

    tba = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned
    groceries_rows = (
        await db_session.execute(
            select(BudgetAssignment).where(BudgetAssignment.category_id == groceries.id)
        )
    ).scalars().all()
    assert {(r.month, r.assigned) for r in groceries_rows} == {
        (AUG, Decimal("100.0000")),
        (SEP, Decimal("50.0000")),
    }
    assert tba == (
        await services.budgets.get_budget_summary(budget.id, SEP)
    ).to_be_assigned - Decimal("0"), "months agree after the round trip"


async def test_undoing_a_repair_restores_the_category_to_the_budget(db_session):
    """User decision, pinned: undoing a hygiene repair brings the category
    back LIVE — with its rows and assignments — rather than re-orphaning
    them, which would deliberately recreate the stranded-money corruption
    the repair exists to fix. The repair UI says so."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Everyday")
    account = await create_account(db_session, budget, "Checking")
    old = await create_category(db_session, budget, group, "Old Hobby")
    await create_transaction(db_session, budget, account, "1000", AUG)
    txn = await create_transaction(db_session, budget, account, "-30", AUG, category=old)
    await create_budget_assignment(db_session, budget, old, AUG, "100")
    old.is_deleted = True  # the pre-PR delete: flag flip, nothing else
    await db_session.flush()

    svc = _service(db_session, services)
    results = await svc.repair_orphans(budget.id, AUG)
    await db_session.flush()
    assert len(results) == 1

    await UndoService(db_session).undo_change(budget.id, results[0].change_id)
    await db_session.flush()

    await db_session.refresh(old)
    await db_session.refresh(txn)
    assert old.is_deleted is False, "the category returns to the budget, alive"
    assert txn.category_id == old.id
    # Not `tba_before_undo - released`: the repair measured against a DEAD
    # envelope (whose current-month assignment already sat outside the
    # summary), while undo resurrects it. The budget is now exactly "live
    # category, $100 assigned, $30 spent, $1000 in" — so TBA is what that
    # budget always shows, and the months agree on it.
    tba_after = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned
    assert tba_after == Decimal("900.0000")
    assert tba_after == (await services.budgets.get_budget_summary(budget.id, SEP)).to_be_assigned


# ─── The referrers the delete clears on its way past ──────────────────────────


async def test_undo_restores_a_saved_view_placement(db_session):
    """The rename bled across a boundary the migration protected.

    `budget_view_placements.is_hidden` is per-view visibility and was
    deliberately left out of the `is_hidden` -> `is_archived` rename. The
    bookkeeping still reached for `is_archived` on it — via a `getattr` default
    that quietly returned False for every placement — and the undo then passed
    `is_archived=` to a constructor that has no such field, so undoing the
    delete of any category placed in a saved view raised `TypeError` instead of
    putting the placement back.
    """
    services = make_services(db_session)
    budget, _group, _account, groceries, _other, _spends = await _setup(db_session)

    view = BudgetView(budget_id=budget.id, name="Need / Want")
    db_session.add(view)
    await db_session.flush()
    db_session.add(
        BudgetViewPlacement(
            view_id=view.id, category_id=groceries.id, sort_order=3, is_hidden=True
        )
    )
    await db_session.flush()

    svc = _service(db_session, services)
    result = await svc.delete_categories(budget.id, [groceries.id], move_to=None, month=AUG)
    await db_session.flush()
    assert await _placement(db_session, view.id, groceries.id) is None

    await UndoService(db_session).undo_change(budget.id, result.change_id)
    await db_session.flush()

    back = await _placement(db_session, view.id, groceries.id)
    assert back is not None
    assert back.sort_order == 3
    # The flag the delete recorded, not the False the broken `getattr` gave
    # every placement regardless of what the user had chosen.
    assert back.is_hidden is True


async def _placement(db_session, view_id, category_id) -> BudgetViewPlacement | None:
    return (
        await db_session.execute(
            select(BudgetViewPlacement).where(
                BudgetViewPlacement.view_id == view_id,
                BudgetViewPlacement.category_id == category_id,
            )
        )
    ).scalar_one_or_none()


# ─── Archiving is undoable too ────────────────────────────────────────────────


async def test_undo_puts_an_archived_envelope_back(db_session):
    """Archive/unarchive record a change row with an action `_apply` had no
    case for, so both fell through to "cannot be undone" — and `undo_newer`,
    which backs the Activity page's "Revert to here", has no per-item handling,
    so one archive anywhere in the range aborted the whole revert."""
    services = make_services(db_session)
    budget, _group, _account, _groceries, other, _spends = await _setup(db_session)
    svc = _service(db_session, services)

    # `other` holds nothing; archiving refuses while an envelope still has money.
    await svc.archive_categories(budget.id, [other.id], month=AUG)
    await db_session.flush()
    await db_session.refresh(other)
    assert other.is_archived is True
    assert other.archived_at is not None

    change = (
        await db_session.execute(
            select(ChangeLog)
            .where(ChangeLog.budget_id == budget.id, ChangeLog.action == "archive")
            .order_by(ChangeLog.created_at.desc())
        )
    ).scalars().first()
    assert change is not None

    await UndoService(db_session).undo_change(budget.id, change.id)
    await db_session.flush()
    await db_session.refresh(other)
    assert other.is_archived is False
    # Cleared, not left stale: a date on a live envelope answers "when was
    # this archived" with something untrue.
    assert other.archived_at is None


async def test_undo_of_a_restore_archives_it_again(db_session):
    """The other direction, so the pair is symmetric rather than one-way."""
    services = make_services(db_session)
    budget, _group, _account, _groceries, other, _spends = await _setup(db_session)
    svc = _service(db_session, services)

    await svc.archive_categories(budget.id, [other.id], month=AUG)
    await svc.unarchive_categories(budget.id, [other.id])
    await db_session.flush()
    await db_session.refresh(other)
    assert other.is_archived is False

    change = (
        await db_session.execute(
            select(ChangeLog)
            .where(ChangeLog.budget_id == budget.id, ChangeLog.action == "unarchive")
            .order_by(ChangeLog.created_at.desc())
        )
    ).scalars().first()
    assert change is not None

    await UndoService(db_session).undo_change(budget.id, change.id)
    await db_session.flush()
    await db_session.refresh(other)
    assert other.is_archived is True
