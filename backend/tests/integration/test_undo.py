"""Undo/audit system: change recording across all write paths, inverse
operations, conflict detection, and the /changes API.

This is the core trust surface — every assertion here is about not losing
or corrupting the user's financial data when they undo something.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import BudgetAssignment, ChangeLog, Transaction
from igab.domain.exceptions import UndoConflict
from igab.services.transaction_service import TransactionCreate, TransactionUpdate
from igab.services.undo_service import UndoService
from tests.integration.factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)

JAN = date(2026, 1, 1)


async def changes_for(session, budget_id, entity_type=None, action=None):
    # sessions run autoflush=False (production commits at request end), so
    # push pending change rows to the DB before reading them back
    await session.flush()
    stmt = select(ChangeLog).where(ChangeLog.budget_id == budget_id)
    if entity_type:
        stmt = stmt.where(ChangeLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(ChangeLog.action == action)
    result = await session.execute(stmt.order_by(ChangeLog.seq))
    return list(result.scalars().all())


async def setup_budget(session, user=None):
    user = user or await create_user(session)
    budget = await create_budget(session, user)
    account = await create_account(session, budget, "Checking")
    group = await create_category_group(session, budget)
    category = await create_category(session, budget, group, "Groceries")
    return budget, account, group, category


# ─── Recording ────────────────────────────────────────────────────────────────


async def test_create_transaction_records_change(db_session):
    budget, account, _, category = await setup_budget(db_session)
    services = make_services(db_session)

    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=account.id,
            date=date(2026, 1, 5),
            amount=Decimal("-42.50"),
            category_id=category.id,
            memo="weekly shop",
        ),
    )

    changes = await changes_for(db_session, budget.id, "transaction")
    assert len(changes) == 1
    change = changes[0]
    assert change.action == "create"
    assert change.entity_id == txn.id
    assert change.source == "manual"
    assert change.before is None
    assert Decimal(change.after["amount"]) == Decimal("-42.50")
    assert change.after["category_id"] == str(category.id)
    assert change.after["memo"] == "weekly shop"
    assert change.undone_at is None


async def test_create_with_record_false_records_nothing(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    services = make_services(db_session)

    await services.transactions.create(
        budget.id,
        TransactionCreate(account_id=account.id, date=JAN, amount=Decimal("-1.00")),
        record=False,
    )

    assert await changes_for(db_session, budget.id) == []


async def test_transfer_create_records_batch(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    savings = await create_account(db_session, budget, "Savings")
    services = make_services(db_session)

    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=account.id,
            date=JAN,
            amount=Decimal("-100.00"),
            transfer_account_id=savings.id,
        ),
    )

    changes = await changes_for(db_session, budget.id, "transaction")
    assert len(changes) == 2
    assert all(c.action == "create" for c in changes)
    assert changes[0].batch_id is not None
    assert changes[0].batch_id == changes[1].batch_id
    assert {c.entity_id for c in changes} == {txn.id, txn.transfer_id}


async def test_split_create_records_batch(db_session):
    budget, account, _, category = await setup_budget(db_session)
    other = await create_category(
        db_session, budget, await create_category_group(db_session, budget), "Fun"
    )
    services = make_services(db_session)

    parent = await services.transactions.create_split(
        budget.id,
        TransactionCreate(account_id=account.id, date=JAN, amount=Decimal("-30.00")),
        [
            TransactionCreate(
                account_id=account.id, date=JAN, amount=Decimal("-20.00"), category_id=category.id
            ),
            TransactionCreate(
                account_id=account.id, date=JAN, amount=Decimal("-10.00"), category_id=other.id
            ),
        ],
    )

    changes = await changes_for(db_session, budget.id, "transaction")
    assert len(changes) == 3  # parent + 2 children
    assert len({c.batch_id for c in changes}) == 1
    parent_change = next(c for c in changes if c.entity_id == parent.id)
    assert parent_change.after["is_split"] is True


async def test_update_records_before_and_after(db_session):
    budget, account, _, category = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN, memo="before-memo")
    services = make_services(db_session)

    await services.transactions.update(
        budget.id,
        txn.id,
        TransactionUpdate(amount=Decimal("-15.00"), category_id=category.id),
    )

    changes = await changes_for(db_session, budget.id, "transaction", "update")
    assert len(changes) == 1
    change = changes[0]
    assert Decimal(change.before["amount"]) == Decimal("-10.00")
    assert change.before["category_id"] is None
    assert Decimal(change.after["amount"]) == Decimal("-15.00")
    assert change.after["category_id"] == str(category.id)
    # untouched fields ride along in both snapshots
    assert change.before["memo"] == "before-memo"
    assert change.after["memo"] == "before-memo"


async def test_noop_update_records_nothing(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN)
    services = make_services(db_session)

    await services.transactions.update(
        budget.id, txn.id, TransactionUpdate(amount=Decimal("-10.00"))
    )

    assert await changes_for(db_session, budget.id, "transaction", "update") == []


async def test_delete_records_and_returns_batch_id(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN)
    services = make_services(db_session)

    batch_id = await services.transactions.delete(budget.id, txn.id)

    changes = await changes_for(db_session, budget.id, "transaction", "delete")
    assert len(changes) == 1
    assert changes[0].batch_id == batch_id
    assert changes[0].entity_id == txn.id
    assert Decimal(changes[0].before["amount"]) == Decimal("-10.00")


async def test_approve_records_only_when_previously_unapproved(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-5.00", JAN, approved=False)
    services = make_services(db_session)

    await services.transactions.approve(txn.id, budget.id)
    await services.transactions.approve(txn.id, budget.id)  # second approve is a no-op

    changes = await changes_for(db_session, budget.id, "transaction", "approve")
    assert len(changes) == 1
    assert changes[0].before["approved"] is False
    assert changes[0].after["approved"] is True


async def test_set_assignment_records_update_with_before(db_session):
    budget, _, _, category = await setup_budget(db_session)
    services = make_services(db_session)

    await services.budgets.set_assignment(budget.id, category.id, JAN, Decimal("100.00"))
    await services.budgets.set_assignment(budget.id, category.id, JAN, Decimal("150.00"))
    # no-op set records nothing
    await services.budgets.set_assignment(budget.id, category.id, JAN, Decimal("150.00"))

    changes = await changes_for(db_session, budget.id, "assignment")
    assert len(changes) == 2
    assert Decimal(changes[0].before["assigned"]) == Decimal("0")
    assert Decimal(changes[0].after["assigned"]) == Decimal("100.00")
    assert Decimal(changes[1].before["assigned"]) == Decimal("100.00")
    assert Decimal(changes[1].after["assigned"]) == Decimal("150.00")


async def test_move_money_records_batch_of_both_sides(db_session):
    budget, _, group, cat_a = await setup_budget(db_session)
    cat_b = await create_category(db_session, budget, group, "Rent")
    await create_budget_assignment(db_session, budget, cat_a, JAN, "200.00")
    services = make_services(db_session)

    await services.budgets.move_money(budget.id, cat_a.id, cat_b.id, Decimal("50.00"), JAN)

    changes = await changes_for(db_session, budget.id, "assignment")
    assert len(changes) == 2
    assert len({c.batch_id for c in changes}) == 1
    assert changes[0].batch_id is not None
    by_cat = {c.after["category_id"]: c for c in changes}
    assert Decimal(by_cat[str(cat_a.id)].after["assigned"]) == Decimal("150.00")
    assert Decimal(by_cat[str(cat_b.id)].after["assigned"]) == Decimal("50.00")


async def test_transaction_merge_records_batch(db_session):
    budget, account, _, category = await setup_budget(db_session)
    payee = await create_payee(db_session, budget, "Store")
    manual = await create_transaction(
        db_session, budget, account, "-20.00", JAN, category=category, payee=payee
    )
    imported = await create_transaction(
        db_session, budget, account, "-20.00", JAN, import_id="imp-1"
    )
    services = make_services(db_session)

    survivor = await services.transactions.merge(
        budget.id, [manual.id, imported.id], survivor_id=manual.id
    )
    assert survivor.id == manual.id

    changes = await changes_for(db_session, budget.id, "transaction")
    assert len(changes) >= 2
    assert len({c.batch_id for c in changes}) == 1
    actions = {c.entity_id: c.action for c in changes}
    assert actions[imported.id] == "delete"


# ─── Undo: service-level inverse operations ───────────────────────────────────


async def test_undo_create_soft_deletes(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    services = make_services(db_session)
    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(account_id=account.id, date=JAN, amount=Decimal("-9.99")),
    )
    [change] = await changes_for(db_session, budget.id, "transaction")

    undo = UndoService(db_session)
    undone = await undo.undo_change(budget.id, change.id)

    assert undone == [change.id]
    await db_session.refresh(txn)
    assert txn.is_deleted is True
    await db_session.refresh(change)
    assert change.undone_at is not None


async def test_undo_delete_restores_all_fields(db_session):
    budget, account, _, category = await setup_budget(db_session)
    payee = await create_payee(db_session, budget, "Grocer")
    txn = await create_transaction(
        db_session,
        budget,
        account,
        "-42.50",
        date(2026, 1, 7),
        category=category,
        payee=payee,
        memo="the memo",
        cleared="cleared",
    )
    services = make_services(db_session)
    batch_id = await services.transactions.delete(budget.id, txn.id)
    await db_session.flush()  # autoflush is off; push the change rows
    await db_session.refresh(txn)
    assert txn.is_deleted is True

    undo = UndoService(db_session)
    await undo.undo_batch(budget.id, batch_id)

    await db_session.refresh(txn)
    assert txn.is_deleted is False
    assert txn.amount == Decimal("-42.50")
    assert txn.category_id == category.id
    assert txn.payee_id == payee.id
    assert txn.memo == "the memo"
    assert txn.cleared == "cleared"
    assert txn.date == date(2026, 1, 7)


async def test_undo_delete_of_transfer_restores_both_sides(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    savings = await create_account(db_session, budget, "Savings")
    services = make_services(db_session)
    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=account.id,
            date=JAN,
            amount=Decimal("-100.00"),
            transfer_account_id=savings.id,
        ),
    )
    partner_id = txn.transfer_id
    batch_id = await services.transactions.delete(budget.id, txn.id)
    await db_session.flush()

    undo = UndoService(db_session)
    await undo.undo_batch(budget.id, batch_id)

    for tid in (txn.id, partner_id):
        row = await db_session.get(Transaction, tid)
        assert row.is_deleted is False


async def test_undo_delete_of_split_restores_parent_and_children(db_session):
    """Deleting a split parent also deletes children; undo must restore all."""
    budget, account, group, category = await setup_budget(db_session)
    other = await create_category(db_session, budget, group, "Fun")
    services = make_services(db_session)

    parent = await services.transactions.create_split(
        budget.id,
        TransactionCreate(account_id=account.id, date=JAN, amount=Decimal("-50.00")),
        [
            TransactionCreate(
                account_id=account.id, date=JAN, amount=Decimal("-30.00"), category_id=category.id
            ),
            TransactionCreate(
                account_id=account.id, date=JAN, amount=Decimal("-20.00"), category_id=other.id
            ),
        ],
    )
    children = await services.transaction_repo.get_splits(parent.id)
    child_ids = [c.id for c in children]

    batch_id = await services.transactions.delete(budget.id, parent.id)
    await db_session.flush()

    # Verify all are deleted
    await db_session.refresh(parent)
    assert parent.is_deleted is True
    for cid in child_ids:
        c = await db_session.get(Transaction, cid)
        assert c.is_deleted is True

    # Undo and verify all restored
    undo = UndoService(db_session)
    await undo.undo_batch(budget.id, batch_id)

    await db_session.refresh(parent)
    assert parent.is_deleted is False
    assert parent.is_split is True
    for cid in child_ids:
        c = await db_session.get(Transaction, cid)
        assert c.is_deleted is False
        assert c.parent_transaction_id == parent.id


async def test_undo_update_restores_before_values(db_session):
    budget, account, _, category = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN, memo="original")
    services = make_services(db_session)
    await services.transactions.update(
        budget.id,
        txn.id,
        TransactionUpdate(amount=Decimal("-99.00"), category_id=category.id, memo="edited"),
    )
    [change] = await changes_for(db_session, budget.id, "transaction", "update")

    undo = UndoService(db_session)
    await undo.undo_change(budget.id, change.id)

    await db_session.refresh(txn)
    assert txn.amount == Decimal("-10.00")
    assert txn.category_id is None
    assert txn.memo == "original"


async def test_undo_approve_restores_unapproved(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-5.00", JAN, approved=False)
    services = make_services(db_session)
    await services.transactions.approve(txn.id, budget.id)
    [change] = await changes_for(db_session, budget.id, "transaction", "approve")

    undo = UndoService(db_session)
    await undo.undo_change(budget.id, change.id)

    await db_session.refresh(txn)
    assert txn.approved is False


async def test_undo_assignment_update_restores_amount(db_session):
    budget, _, _, category = await setup_budget(db_session)
    services = make_services(db_session)
    await services.budgets.set_assignment(budget.id, category.id, JAN, Decimal("100.00"))
    [change] = await changes_for(db_session, budget.id, "assignment")

    undo = UndoService(db_session)
    await undo.undo_change(budget.id, change.id)

    result = await db_session.execute(
        select(BudgetAssignment).where(
            BudgetAssignment.budget_id == budget.id,
            BudgetAssignment.category_id == category.id,
        )
    )
    assignment = result.scalar_one()
    assert assignment.assigned == Decimal("0")


async def test_undo_move_money_batch_restores_both_sides(db_session):
    budget, _, group, cat_a = await setup_budget(db_session)
    cat_b = await create_category(db_session, budget, group, "Rent")
    await create_budget_assignment(db_session, budget, cat_a, JAN, "200.00")
    services = make_services(db_session)
    await services.budgets.move_money(budget.id, cat_a.id, cat_b.id, Decimal("50.00"), JAN)
    changes = await changes_for(db_session, budget.id, "assignment")
    batch_id = changes[0].batch_id

    undo = UndoService(db_session)
    undone = await undo.undo_batch(budget.id, batch_id)
    assert len(undone) == 2

    result = await db_session.execute(
        select(BudgetAssignment).where(BudgetAssignment.budget_id == budget.id)
    )
    by_cat = {a.category_id: a.assigned for a in result.scalars()}
    assert by_cat[cat_a.id] == Decimal("200.00")
    assert by_cat.get(cat_b.id, Decimal("0")) == Decimal("0")


# ─── Undo: conflicts and guards ───────────────────────────────────────────────


async def test_undo_update_conflicts_after_subsequent_edit(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN)
    services = make_services(db_session)
    await services.transactions.update(
        budget.id, txn.id, TransactionUpdate(amount=Decimal("-20.00"))
    )
    first = (await changes_for(db_session, budget.id, "transaction", "update"))[0]
    # a later edit makes the first change stale
    await services.transactions.update(
        budget.id, txn.id, TransactionUpdate(amount=Decimal("-30.00"))
    )

    undo = UndoService(db_session)
    with pytest.raises(UndoConflict) as exc:
        await undo.undo_change(budget.id, first.id)
    assert "amount" in exc.value.fields

    # force overrides staleness and restores the first change's `before`
    await undo.undo_change(budget.id, first.id, force=True)
    await db_session.refresh(txn)
    assert txn.amount == Decimal("-10.00")


async def test_double_undo_conflicts(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN)
    services = make_services(db_session)
    await services.transactions.update(budget.id, txn.id, TransactionUpdate(memo="edited"))
    [change] = await changes_for(db_session, budget.id, "transaction", "update")

    undo = UndoService(db_session)
    await undo.undo_change(budget.id, change.id)
    with pytest.raises(UndoConflict):
        await undo.undo_change(budget.id, change.id)


async def test_reconciled_guard_blocks_undo_even_with_force(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    services = make_services(db_session)
    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(account_id=account.id, date=JAN, amount=Decimal("-10.00")),
    )
    [create_change] = await changes_for(db_session, budget.id, "transaction")
    txn.cleared = "reconciled"
    await db_session.flush()

    undo = UndoService(db_session)
    with pytest.raises(UndoConflict, match="Reconciled"):
        await undo.undo_change(budget.id, create_change.id, force=True)
    await db_session.refresh(txn)
    assert txn.is_deleted is False


async def test_undo_of_an_unlocked_edit_survives_reconciliation(db_session):
    """A memo edit made before the row was reconciled can still be undone —
    reconciliation locks the money, not the bookkeeping — and undoing it must
    not put back the pre-reconciliation `cleared` the snapshot remembers."""
    budget, account, _, _ = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN, memo="lunch")
    services = make_services(db_session)
    await services.transactions.update(budget.id, txn.id, TransactionUpdate(memo="edited"))
    [change] = await changes_for(db_session, budget.id, "transaction", "update")
    txn.cleared = "reconciled"
    await db_session.flush()

    undo = UndoService(db_session)
    await undo.undo_change(budget.id, change.id)
    await db_session.refresh(txn)
    assert txn.memo == "lunch"
    assert txn.cleared == "reconciled", "undo restored the memo, not the old cleared state"


async def test_undo_of_a_money_edit_is_blocked_after_reconciliation(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN)
    services = make_services(db_session)
    await services.transactions.update(
        budget.id, txn.id, TransactionUpdate(amount=Decimal("-12.00"))
    )
    [change] = await changes_for(db_session, budget.id, "transaction", "update")
    txn.cleared = "reconciled"
    await db_session.flush()

    undo = UndoService(db_session)
    with pytest.raises(UndoConflict, match="Reconciled transactions cannot have amount"):
        await undo.undo_change(budget.id, change.id, force=True)
    await db_session.refresh(txn)
    assert txn.amount == Decimal("-12.00")


async def test_undo_create_conflicts_when_entity_edited(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    services = make_services(db_session)
    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(account_id=account.id, date=JAN, amount=Decimal("-10.00")),
    )
    [change] = await changes_for(db_session, budget.id, "transaction")
    txn.memo = "edited since creation"
    await db_session.flush()

    undo = UndoService(db_session)
    with pytest.raises(UndoConflict) as exc:
        await undo.undo_change(budget.id, change.id)
    assert "memo" in exc.value.fields

    await undo.undo_change(budget.id, change.id, force=True)
    await db_session.refresh(txn)
    assert txn.is_deleted is True


async def test_undo_delete_conflicts_when_already_restored(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN)
    services = make_services(db_session)
    batch_id = await services.transactions.delete(budget.id, txn.id)
    txn.is_deleted = False  # user recreated/restored it out of band
    await db_session.flush()

    undo = UndoService(db_session)
    with pytest.raises(UndoConflict, match="no longer deleted"):
        await undo.undo_batch(budget.id, batch_id)


async def test_undo_batch_conflict_leaves_other_items_untouched(db_session):
    """Batch undo is all-or-nothing. The most-recent change in the batch is
    applied first; when it conflicts, nothing else has been touched yet."""
    budget, account, _, _ = await setup_budget(db_session)
    t1 = await create_transaction(db_session, budget, account, "-1.00", JAN)
    t2 = await create_transaction(db_session, budget, account, "-2.00", JAN)
    services = make_services(db_session)

    with services.transactions.changes.batch() as batch_id:
        await services.transactions.delete(budget.id, t1.id)
        await services.transactions.delete(budget.id, t2.id)

    # t2's delete was recorded last → applied first on undo; make it conflict
    t2.is_deleted = False
    await db_session.flush()

    undo = UndoService(db_session)
    with pytest.raises(UndoConflict):
        await undo.undo_batch(budget.id, batch_id)

    await db_session.refresh(t1)
    assert t1.is_deleted is True  # untouched — batch failed before reaching it
    for change in await changes_for(db_session, budget.id, "transaction", "delete"):
        assert change.undone_at is None


async def test_undo_change_in_batch_undoes_whole_batch(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    savings = await create_account(db_session, budget, "Savings")
    services = make_services(db_session)
    txn = await services.transactions.create(
        budget.id,
        TransactionCreate(
            account_id=account.id,
            date=JAN,
            amount=Decimal("-50.00"),
            transfer_account_id=savings.id,
        ),
    )
    changes = await changes_for(db_session, budget.id, "transaction")

    undo = UndoService(db_session)
    undone = await undo.undo_change(budget.id, changes[0].id)  # one half of the pair

    assert set(undone) == {c.id for c in changes}
    for c in changes:
        row = await db_session.get(Transaction, c.entity_id)
        assert row.is_deleted is True


async def test_undo_batch_already_undone_conflicts(db_session):
    budget, account, _, _ = await setup_budget(db_session)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN)
    services = make_services(db_session)
    batch_id = await services.transactions.delete(budget.id, txn.id)
    await db_session.flush()

    undo = UndoService(db_session)
    await undo.undo_batch(budget.id, batch_id)
    with pytest.raises(UndoConflict, match="already been undone"):
        await undo.undo_batch(budget.id, batch_id)


async def test_undo_change_wrong_budget_is_not_found(db_session):
    from igab.domain.exceptions import NotFoundError

    budget, account, _, _ = await setup_budget(db_session)
    other_budget = await create_budget(db_session, await create_user(db_session))
    services = make_services(db_session)
    await services.transactions.create(
        budget.id,
        TransactionCreate(account_id=account.id, date=JAN, amount=Decimal("-1.00")),
    )
    [change] = await changes_for(db_session, budget.id, "transaction")

    undo = UndoService(db_session)
    with pytest.raises(NotFoundError):
        await undo.undo_change(other_budget.id, change.id)


async def test_undo_fails_gracefully_when_entity_hard_deleted(db_session):
    """If the entity row was hard-deleted (not just soft-deleted), undo
    rejects with a clear conflict message, not an internal error."""
    from sqlalchemy import delete

    from igab.db.models import Payee

    budget, _, _, _ = await setup_budget(db_session)
    payee = await create_payee(db_session, budget, "Test Payee")
    services = make_services(db_session)

    # Record a change for this payee (simulating rename via the API)
    from igab.services.change_log import ChangeRecorder, snapshot

    recorder = ChangeRecorder(db_session)
    before = snapshot("payee", payee)
    payee.name = "Renamed"
    await db_session.flush()
    await recorder.record(
        budget_id=budget.id,
        entity_type="payee",
        entity_id=payee.id,
        action="update",
        before=before,
        after=snapshot("payee", payee),
    )
    [change] = await changes_for(db_session, budget.id, "payee")

    # Hard-delete the payee row (bypassing soft-delete)
    await db_session.execute(delete(Payee).where(Payee.id == payee.id))
    await db_session.flush()

    # Undo should fail with "no longer exists", not crash
    undo = UndoService(db_session)
    with pytest.raises(UndoConflict, match="no longer exists"):
        await undo.undo_change(budget.id, change.id)


# ─── API: payee, category, and group recording + undo ─────────────────────────


async def test_payee_create_endpoint_records_only_when_new(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)

    r1 = await api_client.post(f"/api/v1/{budget.id}/payees", json={"name": "Electric Co"})
    assert r1.status_code == 201
    r2 = await api_client.post(f"/api/v1/{budget.id}/payees", json={"name": "Electric Co"})
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]

    changes = await changes_for(db_session, budget.id, "payee")
    assert len(changes) == 1
    assert changes[0].action == "create"
    assert changes[0].after["name"] == "Electric Co"


async def test_payee_update_and_delete_recorded_and_undoable(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    payee = await create_payee(db_session, budget, "Old Name")

    resp = await api_client.patch(f"/api/v1/payees/{payee.id}", json={"name": "New Name"})
    assert resp.status_code == 200
    resp = await api_client.delete(f"/api/v1/payees/{payee.id}")
    assert resp.status_code == 204

    changes = await changes_for(db_session, budget.id, "payee")
    assert [c.action for c in changes] == ["update", "delete"]
    assert changes[0].before["name"] == "Old Name"
    assert changes[0].after["name"] == "New Name"

    # undo the delete via the API
    resp = await api_client.post(f"/api/v1/{budget.id}/changes/{changes[1].id}/undo")
    assert resp.status_code == 200
    await db_session.refresh(payee)
    assert payee.is_deleted is False
    assert payee.name == "New Name"

    # then undo the rename
    resp = await api_client.post(f"/api/v1/{budget.id}/changes/{changes[0].id}/undo")
    assert resp.status_code == 200
    await db_session.refresh(payee)
    assert payee.name == "Old Name"


async def test_payee_merge_undo_moves_back_only_still_on_target(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    source = await create_payee(db_session, budget, "Amazon Mktp")
    target = await create_payee(db_session, budget, "Amazon")
    t1 = await create_transaction(db_session, budget, account, "-10.00", JAN, payee=source)
    t2 = await create_transaction(db_session, budget, account, "-20.00", JAN, payee=source)
    other_payee = await create_payee(db_session, budget, "Somewhere Else")

    resp = await api_client.post(
        f"/api/v1/payees/{source.id}/merge", json={"target_id": str(target.id)}
    )
    assert resp.status_code == 200
    change_id = resp.json()["change_id"]

    await db_session.refresh(source)
    assert source.is_deleted is True
    await db_session.refresh(t1)
    assert t1.payee_id == target.id

    # user re-payees t2 after the merge; undo must not touch it
    t2.payee_id = other_payee.id
    await db_session.flush()

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/{change_id}/undo")
    assert resp.status_code == 200

    await db_session.refresh(source)
    assert source.is_deleted is False
    await db_session.refresh(t1)
    assert t1.payee_id == source.id  # moved back
    await db_session.refresh(t2)
    assert t2.payee_id == other_payee.id  # left alone


async def test_category_group_crud_recorded_and_delete_undoable(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)

    resp = await api_client.post(f"/api/v1/{budget.id}/category-groups", json={"name": "Bills"})
    assert resp.status_code == 201
    group_id = resp.json()["id"]

    resp = await api_client.patch(
        f"/api/v1/category-groups/{group_id}", json={"name": "Monthly Bills"}
    )
    assert resp.status_code == 200
    # no-op patch records nothing
    resp = await api_client.patch(
        f"/api/v1/category-groups/{group_id}", json={"name": "Monthly Bills"}
    )
    assert resp.status_code == 200

    # 200 with a body, not 204: deleting a group is now a real operation that
    # reports what it did and hands back the single change row to undo it.
    # An empty group has nothing to cascade over, so it still records a plain
    # category_group delete.
    resp = await api_client.delete(f"/api/v1/category-groups/{group_id}")
    assert resp.status_code == 200
    assert resp.json()["category_ids"] == []

    changes = await changes_for(db_session, budget.id, "category_group")
    assert [c.action for c in changes] == ["create", "update", "delete"]

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/{changes[2].id}/undo")
    assert resp.status_code == 200
    groups = await api_client.get(f"/api/v1/{budget.id}/category-groups")
    assert any(g["id"] == group_id for g in groups.json())


async def test_category_update_recorded_and_undoable(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    group = await create_category_group(db_session, budget)
    category = await create_category(db_session, budget, group, "Dining")

    resp = await api_client.patch(
        f"/api/v1/categories/{category.id}", json={"name": "Dining Out", "note": "restaurants"}
    )
    assert resp.status_code == 200

    changes = await changes_for(db_session, budget.id, "category")
    assert len(changes) == 1
    assert changes[0].before["name"] == "Dining"

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/{changes[0].id}/undo")
    assert resp.status_code == 200
    await db_session.refresh(category)
    assert category.name == "Dining"
    assert category.note is None


# ─── API: transaction endpoints, bulk, import ─────────────────────────────────


async def test_delete_endpoint_returns_batch_id_and_undo_restores(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    txn = await create_transaction(db_session, budget, account, "-33.00", JAN)

    resp = await api_client.delete(
        f"/api/v1/transactions/{txn.id}", params={"budget_id": str(budget.id)}
    )
    assert resp.status_code == 200
    batch_id = resp.json()["batch_id"]
    assert batch_id

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")
    assert resp.status_code == 200
    await db_session.refresh(txn)
    assert txn.is_deleted is False


async def test_bulk_delete_returns_batch_and_batch_undo_restores_all(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    txns = [
        await create_transaction(db_session, budget, account, f"-{i}.00", JAN) for i in (1, 2, 3)
    ]

    resp = await api_client.post(
        f"/api/v1/{budget.id}/transactions/bulk-delete",
        json={"transaction_ids": [str(t.id) for t in txns]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["updated"]) == 3
    batch_id = body["batch_id"]
    assert batch_id

    for t in txns:
        await db_session.refresh(t)
        assert t.is_deleted is True

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")
    assert resp.status_code == 200
    assert len(resp.json()["undone_change_ids"]) == 3
    for t in txns:
        await db_session.refresh(t)
        assert t.is_deleted is False


async def test_bulk_approve_batch_undo(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    txns = [
        await create_transaction(db_session, budget, account, "-1.00", JAN, approved=False)
        for _ in range(2)
    ]
    already = await create_transaction(db_session, budget, account, "-1.00", JAN, approved=True)

    resp = await api_client.patch(
        f"/api/v1/{budget.id}/transactions/bulk-approve",
        json={"transaction_ids": [str(t.id) for t in [*txns, already]]},
    )
    assert resp.status_code == 200
    batch_id = resp.json()["batch_id"]

    # only the two previously-unapproved got change rows
    changes = await changes_for(db_session, budget.id, "transaction", "approve")
    assert len(changes) == 2

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")
    assert resp.status_code == 200
    for t in txns:
        await db_session.refresh(t)
        assert t.approved is False
    await db_session.refresh(already)
    assert already.approved is True


async def test_csv_import_records_batch_and_undo_removes_all(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)

    csv = "Date,Payee,Amount,Memo\n2026-01-05,Coffee,-4.50,latte\n2026-01-06,Store,-30.00,\n"
    resp = await api_client.post(
        f"/api/v1/{budget.id}/import/csv",
        params={"account_id": str(account.id)},
        files={"file": ("txns.csv", csv.encode(), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2
    batch_id = body["batch_id"]
    assert batch_id

    changes = await changes_for(db_session, budget.id, "transaction", "import")
    assert len(changes) == 2
    assert all(c.source == "import" for c in changes)
    assert all(str(c.batch_id) == batch_id for c in changes)

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{batch_id}/undo")
    assert resp.status_code == 200
    result = await db_session.execute(
        select(Transaction).where(Transaction.account_id == account.id)
    )
    for txn in result.scalars():
        assert txn.is_deleted is True


async def test_csv_reimport_after_dedup_records_no_batch(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    csv = "Date,Payee,Amount,Memo\n2026-01-05,Coffee,-4.50,\n"
    files = {"file": ("txns.csv", csv.encode(), "text/csv")}

    r1 = await api_client.post(
        f"/api/v1/{budget.id}/import/csv", params={"account_id": str(account.id)}, files=files
    )
    assert r1.json()["imported"] == 1
    r2 = await api_client.post(
        f"/api/v1/{budget.id}/import/csv", params={"account_id": str(account.id)}, files=files
    )
    assert r2.json()["imported"] == 0
    assert r2.json()["batch_id"] is None

    changes = await changes_for(db_session, budget.id, "transaction", "import")
    assert len(changes) == 1


# ─── API: /changes listing and error shapes ───────────────────────────────────


async def test_list_changes_pagination_and_order(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    services = make_services(db_session)
    for i in range(1, 6):
        await services.transactions.create(
            budget.id,
            TransactionCreate(account_id=account.id, date=JAN, amount=Decimal(f"-{i}.00")),
        )
    await db_session.flush()

    resp = await api_client.get(f"/api/v1/{budget.id}/changes", params={"limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["changes"]) == 2
    # newest first
    assert Decimal(body["changes"][0]["after"]["amount"]) == Decimal("-5.00")
    assert Decimal(body["changes"][1]["after"]["amount"]) == Decimal("-4.00")

    resp = await api_client.get(f"/api/v1/{budget.id}/changes", params={"limit": 2, "offset": 4})
    assert len(resp.json()["changes"]) == 1
    assert Decimal(resp.json()["changes"][0]["after"]["amount"]) == Decimal("-1.00")


async def test_undo_endpoint_conflict_shape(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    txn = await create_transaction(db_session, budget, account, "-10.00", JAN)
    services = make_services(db_session)
    await services.transactions.update(
        budget.id, txn.id, TransactionUpdate(amount=Decimal("-20.00"))
    )
    [change] = await changes_for(db_session, budget.id, "transaction", "update")
    txn.amount = Decimal("-99.00")
    await db_session.flush()

    resp = await api_client.post(f"/api/v1/{budget.id}/changes/{change.id}/undo")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "edited since" in detail["message"]
    assert "amount" in detail["fields"]

    resp = await api_client.post(
        f"/api/v1/{budget.id}/changes/{change.id}/undo", params={"force": "true"}
    )
    assert resp.status_code == 200
    await db_session.refresh(txn)
    assert txn.amount == Decimal("-10.00")


async def test_undo_endpoint_unknown_change_404(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    resp = await api_client.post(f"/api/v1/{budget.id}/changes/{uuid.uuid4()}/undo")
    assert resp.status_code == 404
    resp = await api_client.post(f"/api/v1/{budget.id}/changes/batch/{uuid.uuid4()}/undo")
    assert resp.status_code == 404


async def test_changes_scoped_to_budget(api_client, db_session):
    budget = await create_budget(db_session, api_client.test_user)
    other = await create_budget(db_session, api_client.test_user)
    account = await create_account(db_session, budget)
    services = make_services(db_session)
    await services.transactions.create(
        budget.id,
        TransactionCreate(account_id=account.id, date=JAN, amount=Decimal("-1.00")),
    )

    resp = await api_client.get(f"/api/v1/{other.id}/changes")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
