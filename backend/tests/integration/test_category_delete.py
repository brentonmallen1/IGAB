"""Deleting a category as a real operation.

The numbers in `test_future_assignment_no_longer_strands_money` are the ones
that made this work necessary: measured against the old one-line soft delete,
the same budget reported Ready to Assign as 900 in August and 950 in September,
because a September assignment on a deleted category stayed subtracted from
August's TBA while belonging to no envelope on screen.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import (
    BudgetAssignment,
    BudgetFilterCategory,
    BudgetViewPlacement,
    Category,
    CategoryTarget,
)
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.category_service import CategoryService

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


async def _budget_with_groceries(db_session):
    """$1000 in, $100 assigned to Groceries in August, $40 spent there."""
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Everyday")
    account = await create_account(db_session, budget, "Checking")
    groceries = await create_category(db_session, budget, group, "Groceries")
    other = await create_category(db_session, budget, group, "Other")

    await create_transaction(db_session, budget, account, "1000", AUG)
    await create_budget_assignment(db_session, budget, groceries, AUG, "100")
    spend = await create_transaction(
        db_session, budget, account, "-40", date(2026, 8, 10), category=groceries
    )
    await db_session.flush()
    return budget, group, account, groceries, other, spend


# ─── Money ────────────────────────────────────────────────────────────────────


async def test_available_returns_to_ready_to_assign(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, _, _ = await _budget_with_groceries(db_session)

    before = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned
    await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    after = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned

    # $60 was sitting in the envelope; deleting it hands that back.
    assert after - before == Decimal("60")


async def test_future_assignment_no_longer_strands_money(db_session):
    """The headline defect: TBA must not depend on which month is on screen.

    `get_budget_summary` states this invariant in its own docstring, and the
    old delete broke it — the September assignment stayed deducted from August
    while its category was gone from every listing.
    """
    services = make_services(db_session)
    budget, _, _, groceries, _, _ = await _budget_with_groceries(db_session)
    await create_budget_assignment(db_session, budget, groceries, SEP, "50")
    await db_session.flush()

    aug_before = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned
    sep_before = (await services.budgets.get_budget_summary(budget.id, SEP)).to_be_assigned
    assert aug_before == sep_before

    await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)

    aug_after = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned
    sep_after = (await services.budgets.get_budget_summary(budget.id, SEP)).to_be_assigned
    assert aug_after == sep_after, "Ready to Assign disagrees between months after a delete"
    # $60 available + $50 that was stranded in September.
    assert aug_after - aug_before == Decimal("110")


async def test_assigned_total_stops_silently_dropping(db_session):
    """August's Assigned total counted $110 before and $10 after — money that
    really was assigned and really was spent simply stopped being counted.
    Removing the assignment row makes the drop a fact rather than an artifact."""
    services = make_services(db_session)
    budget, _, _, groceries, _, _ = await _budget_with_groceries(db_session)

    svc = _service(db_session, services)
    result = await svc.delete_categories(budget.id, [groceries.id], month=AUG)

    summary = await services.budgets.get_budget_summary(budget.id, AUG)
    assert summary.total_assigned == Decimal("0")
    assert result.assignments_removed == 1
    # `released` is what actually reaches Ready to Assign, not the sum of the
    # assignment rows removed. $100 was assigned but $40 of it was spent, and
    # spent money does not come back — only the $60 still in the envelope does.
    # Reporting 100 in the toast would be the dialog lying about money.
    assert result.released == Decimal("60")


async def test_zero_sum_preserved_when_moving(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, other, _ = await _budget_with_groceries(db_session)
    await create_budget_assignment(db_session, budget, other, AUG, "10")
    await db_session.flush()

    before = await services.budgets.get_budget_summary(budget.id, AUG)
    total_before = before.to_be_assigned + sum(b.available for b in before.category_balances)

    await _service(db_session, services).delete_categories(
        budget.id, [groceries.id], move_to=other.id, month=AUG
    )

    after = await services.budgets.get_budget_summary(budget.id, AUG)
    total_after = after.to_be_assigned + sum(b.available for b in after.category_balances)
    assert total_after == total_before


# ─── Transactions ─────────────────────────────────────────────────────────────


async def test_uncategorize_makes_rows_findable(db_session):
    """The old delete left `category_id` set, so `needs_category` was False and
    the row appeared in no filter and no badge — invisible work."""
    services = make_services(db_session)
    budget, _, _, groceries, _, spend = await _budget_with_groceries(db_session)

    await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.refresh(spend)

    assert spend.category_id is None
    assert spend.prior_category_id == groceries.id
    assert spend.prior_category_name == "Groceries"

    rows, _count, _sum = await services.transactions.transaction_repo.list_for_budget(
        budget.id, uncategorized=True
    )
    assert spend.id in {r.id for r in rows}

    # And the server now says so on the row itself, which is what the badge,
    # the filter and the amber chip all read.
    refreshed = await services.transactions.transaction_repo.get(spend.id)
    assert refreshed is not None and refreshed.needs_category is True


async def test_move_to_files_rows_in_the_target(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, other, spend = await _budget_with_groceries(db_session)

    result = await _service(db_session, services).delete_categories(
        budget.id, [groceries.id], move_to=other.id, month=AUG
    )
    await db_session.refresh(spend)

    assert spend.category_id == other.id
    assert result.transactions_moved == 1
    assert result.transactions_uncategorized == 0
    # Provenance is written on both paths so undo can find its own rows; the
    # register decides whether to *show* it from category_id being null.
    assert spend.prior_category_id == groceries.id


async def test_reconciled_rows_are_cleared_too(db_session):
    """Reconciliation asserts amount, date and cleared status agree with the
    bank — none of which a category affects. Leaving reconciled rows behind
    would strand the oldest history on a category that no longer exists, and
    `TransactionService.update` refuses to re-file them by hand."""
    services = make_services(db_session)
    budget, _, account, groceries, _, _ = await _budget_with_groceries(db_session)
    locked = await create_transaction(
        db_session,
        budget,
        account,
        "-7",
        date(2026, 8, 12),
        category=groceries,
        cleared="reconciled",
    )
    await db_session.flush()

    balance_before = await services.account_repo.get_balance(account.id)
    await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.refresh(locked)

    assert locked.category_id is None
    assert locked.cleared == "reconciled", "the delete must not unreconcile anything"
    assert await services.account_repo.get_balance(account.id) == balance_before


async def test_split_children_follow_and_parent_keeps_no_category(db_session):
    services = make_services(db_session)
    budget, _, account, groceries, _, _ = await _budget_with_groceries(db_session)
    parent = await create_transaction(
        db_session, budget, account, "-30", date(2026, 8, 15), is_split=True
    )
    child = await create_transaction(
        db_session,
        budget,
        account,
        "-30",
        date(2026, 8, 15),
        category=groceries,
        parent_transaction_id=parent.id,
    )
    await db_session.flush()

    await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.refresh(parent)
    await db_session.refresh(child)

    assert child.category_id is None
    assert child.prior_category_id == groceries.id
    assert parent.category_id is None
    assert parent.prior_category_id is None, "a split parent never carried a category"


async def test_soft_deleted_transactions_are_cleared_as_well(db_session):
    """Restoring a deleted transaction must not resurrect a dead category."""
    services = make_services(db_session)
    budget, _, account, groceries, _, _ = await _budget_with_groceries(db_session)
    gone = await create_transaction(
        db_session,
        budget,
        account,
        "-3",
        date(2026, 8, 18),
        category=groceries,
        is_deleted=True,
    )
    await db_session.flush()

    result = await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.refresh(gone)

    assert gone.category_id is None
    # …but it is not counted in what the user was told would happen.
    assert result.transactions_uncategorized == 1


# ─── Preview ──────────────────────────────────────────────────────────────────


async def test_preview_equals_what_the_delete_does(db_session):
    """A confirmation that misreports money is worse than none at all.

    This is the differential test: whatever the dialog is about to say, the
    delete must then do.
    """
    services = make_services(db_session)
    budget, _, account, groceries, _, _ = await _budget_with_groceries(db_session)
    await create_budget_assignment(db_session, budget, groceries, SEP, "50")
    await create_transaction(
        db_session, budget, account, "-9", date(2026, 8, 20), category=groceries
    )
    payee = await create_payee(db_session, budget, "Corner Store")
    payee.default_category_id = groceries.id
    sched = await create_scheduled_transaction(db_session, budget, account, "-25", "monthly", AUG)
    sched.category_id = groceries.id
    await db_session.flush()

    svc = _service(db_session, services)
    preview = await svc.preview_delete(budget.id, [groceries.id], AUG)

    assert preview.transaction_count == 2
    assert preview.payee_count == 1
    assert preview.scheduled_count == 1
    assert preview.future_assigned == Decimal("50")
    assert not preview.is_empty

    tba_before = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned
    result = await svc.delete_categories(budget.id, [groceries.id], month=AUG)
    tba_after = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned

    assert result.transactions_uncategorized == preview.transaction_count
    # What the dialog said would come back to Ready to Assign, did.
    assert tba_after - tba_before == preview.available + preview.future_assigned


async def test_preview_reports_an_empty_category_as_empty(db_session):
    """Nothing to decide means the client may skip the dialog entirely."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Everyday")
    spare = await create_category(db_session, budget, group, "Spare")
    await db_session.flush()

    preview = await _service(db_session, services).preview_delete(budget.id, [spare.id], AUG)
    assert preview.is_empty
    assert preview.blocked_by == []


async def test_preview_counts_reconciled_separately(db_session):
    services = make_services(db_session)
    budget, _, account, groceries, _, _ = await _budget_with_groceries(db_session)
    await create_transaction(
        db_session,
        budget,
        account,
        "-7",
        date(2026, 8, 12),
        category=groceries,
        cleared="reconciled",
    )
    await db_session.flush()

    preview = await _service(db_session, services).preview_delete(budget.id, [groceries.id], AUG)
    assert preview.transaction_count == 2
    assert preview.reconciled_count == 1


# ─── Referrers ────────────────────────────────────────────────────────────────


async def test_every_referrer_is_cleared_or_deliberately_left(db_session):
    """One assertion per row of the plan's referrer table.

    A referrer added later without a decision fails here rather than leaking
    into production as another silent pointer at a deleted category.
    """
    services = make_services(db_session)
    budget, group, account, groceries, _, _ = await _budget_with_groceries(db_session)

    payee = await create_payee(db_session, budget, "Corner Store")
    payee.default_category_id = groceries.id
    sched = await create_scheduled_transaction(db_session, budget, account, "-25", "monthly", AUG)
    sched.category_id = groceries.id
    target = CategoryTarget(
        category_id=groceries.id, target_type="monthly", target_amount=Decimal("100")
    )
    db_session.add(target)
    await db_session.flush()

    await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)
    await db_session.refresh(payee)
    await db_session.refresh(sched)

    # Cleared
    assert payee.default_category_id is None
    assert sched.category_id is None
    assert (
        await db_session.execute(
            select(BudgetAssignment).where(BudgetAssignment.category_id == groceries.id)
        )
    ).scalars().first() is None
    assert (
        await db_session.execute(
            select(BudgetViewPlacement).where(BudgetViewPlacement.category_id == groceries.id)
        )
    ).scalars().first() is None
    assert (
        await db_session.execute(
            select(BudgetFilterCategory).where(BudgetFilterCategory.category_id == groceries.id)
        )
    ).scalars().first() is None

    # Deliberately left: the target returns intact with the category on undo.
    survivor = (
        (
            await db_session.execute(
                select(CategoryTarget).where(CategoryTarget.category_id == groceries.id)
            )
        )
        .scalars()
        .first()
    )
    assert survivor is not None


async def test_auto_categorize_never_returns_a_deleted_category(db_session):
    """The orphan population used to grow on its own: a new transaction for
    the payee was auto-filed straight back into the dead envelope."""
    services = make_services(db_session)
    budget, _, account, groceries, _, _ = await _budget_with_groceries(db_session)
    payee = await create_payee(db_session, budget, "Corner Store")
    await create_transaction(
        db_session, budget, account, "-11", date(2026, 8, 5), category=groceries, payee=payee
    )
    await db_session.flush()

    found = await services.transactions.transaction_repo.get_most_recent_category_for_payee(
        budget.id, payee.id
    )
    assert found == groceries.id

    await _service(db_session, services).delete_categories(budget.id, [groceries.id], month=AUG)

    after = await services.transactions.transaction_repo.get_most_recent_category_for_payee(
        budget.id, payee.id
    )
    assert after is None


# ─── Linked categories ────────────────────────────────────────────────────────


async def test_delete_refused_for_a_live_cards_payment_category(db_session):
    """Not symmetric with account deletion, deliberately: deleting the account
    unlinks the category because the account is what is leaving. Deleting the
    category would leave a live card with no payment envelope."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Debt")
    card = await create_account(db_session, budget, "Visa", account_type="credit_card")
    payment = await create_category(db_session, budget, group, "Visa Payment")
    payment.linked_account_id = card.id
    await db_session.flush()

    with pytest.raises(InvariantViolation, match="payment category for Visa"):
        await _service(db_session, services).delete_categories(budget.id, [payment.id], month=AUG)

    await db_session.refresh(payment)
    assert payment.is_deleted is False


async def test_delete_allowed_once_the_account_is_gone(db_session):
    """A link to an already-deleted counterpart is stale, not load-bearing —
    and `AccountRepository.soft_delete` clears it on the way out anyway."""
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Debt")
    card = await create_account(db_session, budget, "Visa", account_type="credit_card")
    payment = await create_category(db_session, budget, group, "Visa Payment")
    payment.linked_account_id = card.id
    await db_session.flush()

    await services.account_repo.soft_delete(card.id)
    await db_session.refresh(payment)
    assert payment.linked_account_id is None, "account delete still unlinks its category"

    await _service(db_session, services).delete_categories(budget.id, [payment.id], month=AUG)
    await db_session.refresh(payment)
    assert payment.is_deleted is True


async def test_a_deleted_category_never_holds_a_link(db_session):
    """The invariant that keeps undo simple.

    Because `_blocking_link` refuses while the counterpart is live, and both
    counterpart deletions clear the link on their way out
    (`AccountRepository.soft_delete`, `delete_liability`), a category can only
    reach `is_deleted` with null bindings. That is why `_undo_category_delete`
    needs no contested-link handling. If a future change lets a linked
    category be deleted, this fails and that reasoning has to be revisited.
    """
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    group = await create_category_group(db_session, budget, "Debt")
    card = await create_account(db_session, budget, "Visa", account_type="credit_card")
    payment = await create_category(db_session, budget, group, "Visa Payment")
    payment.linked_account_id = card.id
    await db_session.flush()

    # Route 1: the account goes first and unlinks the category itself.
    await services.account_repo.soft_delete(card.id)
    await db_session.refresh(payment)
    assert payment.linked_account_id is None

    await _service(db_session, services).delete_categories(budget.id, [payment.id], month=AUG)
    await db_session.refresh(payment)
    assert payment.is_deleted is True
    assert payment.linked_account_id is None
    assert payment.linked_liability_id is None

    # Route 2: there is no other route — a live link refuses, as its own test
    # above shows. Sweep every deleted category in the budget to be sure.
    deleted = (
        (
            await db_session.execute(
                select(Category).where(
                    Category.budget_id == budget.id,
                    Category.is_deleted == True,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    assert deleted
    for cat in deleted:
        assert cat.linked_account_id is None
        assert cat.linked_liability_id is None


async def test_move_target_must_be_categorizable(db_session):
    services = make_services(db_session)
    budget, group, _, groceries, _, _ = await _budget_with_groceries(db_session)
    card = await create_account(db_session, budget, "Visa", account_type="credit_card")
    payment = await create_category(db_session, budget, group, "Visa Payment")
    payment.linked_account_id = card.id
    await db_session.flush()

    with pytest.raises(InvariantViolation, match="cannot be filed"):
        await _service(db_session, services).delete_categories(
            budget.id, [groceries.id], move_to=payment.id
        )


async def test_cannot_move_into_a_category_being_deleted(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, _, _ = await _budget_with_groceries(db_session)

    with pytest.raises(InvariantViolation, match="being deleted"):
        await _service(db_session, services).delete_categories(
            budget.id, [groceries.id], move_to=groceries.id
        )


async def test_move_target_from_another_budget_is_refused(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, _, _ = await _budget_with_groceries(db_session)
    other_user = await create_user(db_session)
    other_budget = await create_budget(db_session, other_user)
    other_group = await create_category_group(db_session, other_budget, "Theirs")
    foreign = await create_category(db_session, other_budget, other_group, "Foreign")
    await db_session.flush()

    with pytest.raises(InvariantViolation, match="does not belong to this budget"):
        await _service(db_session, services).delete_categories(
            budget.id, [groceries.id], move_to=foreign.id
        )


# ─── Groups ───────────────────────────────────────────────────────────────────


async def test_group_delete_leaves_nothing_live_underneath(db_session):
    """The sharper half of the old bug: the group went, its categories stayed
    live and off screen, and their balances went on reducing Ready to Assign."""
    services = make_services(db_session)
    budget, group, _, groceries, other, _ = await _budget_with_groceries(db_session)

    await _service(db_session, services).delete_group(budget.id, group.id, month=AUG)

    live = (
        (
            await db_session.execute(
                select(Category).where(
                    Category.category_group_id == group.id,
                    Category.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    assert list(live) == []

    summary = await services.budgets.get_budget_summary(budget.id, AUG)
    assert summary.category_balances == []


async def test_group_delete_moves_transactions_when_asked(db_session):
    services = make_services(db_session)
    budget, group, _, groceries, _, spend = await _budget_with_groceries(db_session)
    keep_group = await create_category_group(db_session, budget, "Keep")
    destination = await create_category(db_session, budget, keep_group, "Destination")
    await db_session.flush()

    await _service(db_session, services).delete_group(budget.id, group.id, move_to=destination.id)
    await db_session.refresh(spend)
    assert spend.category_id == destination.id


async def test_system_group_cannot_be_deleted(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    system = await create_category_group(db_session, budget, "Income", is_system=True)
    await db_session.flush()

    with pytest.raises(InvariantViolation, match="system category groups"):
        await _service(db_session, services).delete_group(budget.id, system.id)


async def test_empty_group_still_deletes(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    empty = await create_category_group(db_session, budget, "Empty")
    await db_session.flush()

    result = await _service(db_session, services).delete_group(budget.id, empty.id)
    await db_session.refresh(empty)
    assert empty.is_deleted is True
    assert result.category_ids == []


async def test_deleting_an_unknown_category_raises(db_session):
    services = make_services(db_session)
    budget, _, _, _, _, _ = await _budget_with_groceries(db_session)

    with pytest.raises(NotFoundError):
        await _service(db_session, services).delete_categories(budget.id, [uuid.uuid4()])


# ─── Repairing orphans left by the old delete ─────────────────────────────────


async def _orphan_the_old_way(db_session, category) -> None:
    """Reproduce what the one-line soft delete used to leave behind: the flag
    flipped and every referrer still pointing at it."""
    category.is_deleted = True
    await db_session.flush()


async def test_repair_finds_and_fixes_orphans_from_the_old_delete(db_session):
    services = make_services(db_session)
    budget, _, account, groceries, _, spend = await _budget_with_groceries(db_session)
    await create_budget_assignment(db_session, budget, groceries, SEP, "50")
    payee = await create_payee(db_session, budget, "Corner Store")
    payee.default_category_id = groceries.id
    await _orphan_the_old_way(db_session, groceries)

    from igab.services.integrity_service import IntegrityService

    report = await IntegrityService(db_session).run(budget.id)
    orphans = next(c for c in report.checks if c.name == "orphaned_categories")
    assert orphans.passed is False

    tba_before = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned
    results = await _service(db_session, services).repair_orphans(budget.id, AUG)
    tba_after = (await services.budgets.get_budget_summary(budget.id, AUG)).to_be_assigned

    assert len(results) == 1
    assert results[0].transactions_uncategorized == 1
    assert results[0].assignments_removed == 2
    # Only $50 moves. The old delete already hid the category from the summary,
    # so August's $100 stopped counting against Ready to Assign back then; what
    # stayed stranded was the September assignment, still deducted from August's
    # TBA with no envelope on screen holding it. That is the money that returns.
    assert results[0].released == Decimal("50")
    assert tba_after - tba_before == Decimal("50")

    await db_session.refresh(spend)
    await db_session.refresh(payee)
    assert spend.category_id is None
    assert spend.prior_category_name == "Groceries"
    assert payee.default_category_id is None

    report = await IntegrityService(db_session).run(budget.id)
    orphans = next(c for c in report.checks if c.name == "orphaned_categories")
    assert orphans.passed is True


async def test_repair_is_idempotent(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, _, _ = await _budget_with_groceries(db_session)
    await _orphan_the_old_way(db_session, groceries)

    svc = _service(db_session, services)
    first = await svc.repair_orphans(budget.id, AUG)
    second = await svc.repair_orphans(budget.id, AUG)

    assert len(first) == 1
    assert second == [], "a second run must find nothing left to do"


async def test_repair_leaves_a_properly_deleted_category_alone(db_session):
    services = make_services(db_session)
    budget, _, _, groceries, _, _ = await _budget_with_groceries(db_session)

    svc = _service(db_session, services)
    await svc.delete_categories(budget.id, [groceries.id], month=AUG)
    assert await svc.repair_orphans(budget.id, AUG) == []


async def test_integrity_reports_categories_under_a_deleted_group(db_session):
    """The other half of the class: live envelopes the grid cannot draw,
    because it renders only the groups it was given."""
    services = make_services(db_session)
    budget, group, _, _, _, _ = await _budget_with_groceries(db_session)
    group.is_deleted = True
    await db_session.flush()

    from igab.services.integrity_service import IntegrityService

    report = await IntegrityService(db_session).run(budget.id)
    orphans = next(c for c in report.checks if c.name == "orphaned_categories")
    assert orphans.passed is False
    assert any("under a deleted group" in d for d in orphans.details)

    # Reported, not silently repaired — restoring the group or deleting the
    # categories deliberately are both defensible, and this action cannot pick.
    svc = _service(db_session, services)
    assert await svc.count_orphaned_categories_under_deleted_groups(budget.id) == 2


# ─── Moving takes the cover along ────────────────────────────────────────────


JUN = date(2026, 6, 1)
JUL = date(2026, 7, 1)
OCT = date(2026, 10, 1)


class TestMoveTakesItsCover:
    """Measured before this existed: delete Groceries ($100 assigned, $40
    spent) moving its rows to Dining — the dialog promised $60, the delete
    released $100, and Dining went $40 overspent, undisclosed. The rule now:
    the assignment that covered the moved spending moves with it, month by
    month, so the destination's balance is untouched and what reaches Ready
    to Assign is exactly what the dialog said, on both paths.
    """

    async def _rich_setup(self, db_session):
        """A source with an awkward history: overspent June (no assignment,
        covered from TBA), normal August, a future assignment, and a
        refund-heavy October — every shape the cover has to survive."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        group = await create_category_group(db_session, budget, "Everyday")
        account = await create_account(db_session, budget, "Checking")
        a = await create_category(db_session, budget, group, "Groceries")
        b = await create_category(db_session, budget, group, "Dining")
        await create_transaction(db_session, budget, account, "1000", JUN)
        # B's own life, which must come through untouched.
        await create_budget_assignment(db_session, budget, b, JUL, "50")
        await create_transaction(db_session, budget, account, "-20", JUL, category=b)
        # A's history.
        await create_transaction(db_session, budget, account, "-10", JUN, category=a)
        await create_budget_assignment(db_session, budget, a, AUG, "100")
        await create_transaction(db_session, budget, account, "-40", AUG, category=a)
        await create_budget_assignment(db_session, budget, a, SEP, "50")
        await create_transaction(db_session, budget, account, "30", OCT, category=a)
        await db_session.flush()
        return budget, a, b

    async def test_move_releases_what_the_dialog_promised(self, db_session):
        services = make_services(db_session)
        budget, a, b = await self._rich_setup(db_session)
        svc = _service(db_session, services)

        preview = await svc.preview_delete(budget.id, [a.id], AUG)

        result = await svc.delete_categories(budget.id, [a.id], move_to=b.id, month=AUG)
        assert result.released == preview.released_if_moved, (
            "the dialog's number and the delete's number are the same rule"
        )
        # The two modes legitimately differ here: October's refund is future
        # activity, and its cover is a future assignment the viewed month's
        # TBA already counts. Stated and pinned, not silent.
        assert preview.released_if_moved == preview.released_if_uncategorized + Decimal("30")

    async def test_move_holds_the_destination_harmless_in_every_month(self, db_session):
        """Not just the viewed month: the cover is keyed to activity months,
        so every per-month delta to the destination nets zero all the way
        through the carryover simulation — overspent June, refund October and
        all."""
        services = make_services(db_session)
        budget, a, b = await self._rich_setup(db_session)
        months = (JUN, JUL, AUG, SEP, OCT)
        before = {
            m: (await services.budgets.get_category_balance(b.id, m)).available for m in months
        }

        await _service(db_session, services).delete_categories(
            budget.id, [a.id], move_to=b.id, month=AUG
        )
        db_session.expunge_all()

        for m in months:
            after = (await services.budgets.get_category_balance(b.id, m)).available
            assert after == before[m], f"destination moved in {m:%B}: {before[m]} -> {after}"

    async def test_uncategorize_still_releases_what_it_promised(self, db_session):
        """The same promise holds on the other path — one rule, two modes."""
        services = make_services(db_session)
        budget, a, b = await self._rich_setup(db_session)
        svc = _service(db_session, services)

        preview = await svc.preview_delete(budget.id, [a.id], AUG)

        result = await svc.delete_categories(budget.id, [a.id], month=AUG)
        assert result.released == preview.released_if_uncategorized

    async def test_preview_names_the_spending_that_moves(self, db_session):
        services = make_services(db_session)
        budget, a, b = await self._rich_setup(db_session)

        preview = await _service(db_session, services).preview_delete(budget.id, [a.id], AUG)
        # −10 (Jun) −40 (Aug) +30 (Oct refund) → net 20 of spending.
        assert preview.moving_activity == Decimal("20")

    async def test_a_group_cascade_covers_each_categorys_months(self, db_session):
        """Two categories with activity in different months, moved as one
        cascade — the destination is harmless against their combined
        history."""
        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        group = await create_category_group(db_session, budget, "Food")
        keep = await create_category_group(db_session, budget, "Keep")
        account = await create_account(db_session, budget, "Checking")
        groceries = await create_category(db_session, budget, group, "Groceries")
        dining = await create_category(db_session, budget, group, "Dining")
        landing = await create_category(db_session, budget, keep, "Everything")
        await create_transaction(db_session, budget, account, "500", JUN)
        await create_budget_assignment(db_session, budget, groceries, JUN, "30")
        await create_transaction(db_session, budget, account, "-30", JUN, category=groceries)
        await create_budget_assignment(db_session, budget, dining, AUG, "60")
        await create_transaction(db_session, budget, account, "-25", AUG, category=dining)
        await db_session.flush()

        months = (JUN, JUL, AUG)
        before = {
            m: (await services.budgets.get_category_balance(landing.id, m)).available
            for m in months
        }
        await _service(db_session, services).delete_group(
            budget.id, group.id, move_to=landing.id, month=AUG
        )
        db_session.expunge_all()
        for m in months:
            after = (await services.budgets.get_category_balance(landing.id, m)).available
            assert after == before[m]
