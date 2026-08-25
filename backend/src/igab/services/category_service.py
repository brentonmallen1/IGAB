"""Deleting a category as a real operation.

A category is referenced by nine tables, and none of their ``ON DELETE``
clauses fire on a soft delete. Flipping ``is_deleted`` and stopping — which is
what this replaced — left every one of them pointing at a category the budget
no longer shows, and the app then disagreed with itself in ways that all cost
the user trust:

- assignments in future months stayed subtracted from Ready to Assign with no
  envelope on screen holding the money, so TBA differed between two months of
  the same budget;
- transactions kept a ``category_id``, so ``NEEDS_CATEGORY`` (which tests
  ``category_id IS NULL``) reported them as filed — absent from the badge,
  absent from the Uncategorized filter, drawn as a bare dash;
- payee defaults and scheduled transactions kept re-filing *new* rows into the
  dead envelope, so the population grew on its own.

``AccountRepository.soft_delete`` already does this properly for accounts — it
soft-deletes their transactions and hand-clears the CC-payment category's link
precisely because "the FK's ON DELETE SET NULL only fires on hard deletes".
This is the same job for the other side of that relationship.

**Everything here is recorded as one change-log row**, not one per affected
transaction. See :meth:`_record_delete`.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import (
    BudgetAssignment,
    BudgetFilterCategory,
    BudgetViewPlacement,
    Category,
    CategoryGroup,
    Payee,
    ScheduledTransaction,
    Transaction,
)
from igab.domain.dates import month_start as first_of_month
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository
from igab.services.budget_service import BudgetService
from igab.services.change_log import ChangeRecorder, snapshot


@dataclass
class CategoryDeletePreview:
    """What a delete is about to do, so the dialog can say it before it does.

    Pinned against the real thing by a differential test: a dialog that
    misreports money is the same failure as a badge that says 3 over a
    register drawing 930.
    """

    category_ids: list[uuid.UUID] = field(default_factory=list)
    category_names: list[str] = field(default_factory=list)
    transaction_count: int = 0
    reconciled_count: int = 0
    #: Available balance returning to Ready to Assign in the viewed month.
    available: Decimal = Decimal("0")
    #: Assigned in months after the viewed one — money currently deducted from
    #: TBA with nothing on screen holding it once the category goes.
    future_assigned: Decimal = Decimal("0")
    payee_count: int = 0
    scheduled_count: int = 0
    #: Non-empty only when something blocks the delete outright.
    blocked_by: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Nothing to decide — the client may skip the dialog entirely."""
        return (
            self.transaction_count == 0
            and self.available == 0
            and self.future_assigned == 0
            and self.payee_count == 0
            and self.scheduled_count == 0
        )


def _touched(bookkeeping: dict[str, Any]) -> bool:
    """Did the repair actually clear anything for this category?"""
    return any(
        bookkeeping.get(key)
        for key in ("_payee_ids", "_scheduled_ids", "_placements", "_filter_selections")
    )


@dataclass
class CategoryDeleteResult:
    change_id: uuid.UUID
    category_ids: list[uuid.UUID]
    transactions_moved: int
    transactions_uncategorized: int
    assignments_removed: int
    released: Decimal


class CategoryService:
    def __init__(
        self,
        session: AsyncSession,
        category_repo: CategoryRepository,
        group_repo: CategoryGroupRepository,
        budget_service: BudgetService,
    ) -> None:
        self.session = session
        self.category_repo = category_repo
        self.group_repo = group_repo
        self.budget_service = budget_service
        self.changes = ChangeRecorder(session)

    # ─── Preview ──────────────────────────────────────────────────────────────

    async def preview_delete(
        self, budget_id: uuid.UUID, category_ids: list[uuid.UUID], month: date
    ) -> CategoryDeletePreview:
        cats = await self._live_categories(budget_id, category_ids)
        preview = CategoryDeletePreview(
            category_ids=[c.id for c in cats],
            category_names=[c.name for c in cats],
            blocked_by=[m for c in cats if (m := await self._blocking_link(c))],
        )
        if not cats:
            return preview

        ids = [c.id for c in cats]
        month_start = first_of_month(month)

        preview.transaction_count = await self._count(
            select(Transaction.id).where(
                Transaction.category_id.in_(ids),
                Transaction.is_deleted == False,  # noqa: E712
            )
        )
        preview.reconciled_count = await self._count(
            select(Transaction.id).where(
                Transaction.category_id.in_(ids),
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.cleared == "reconciled",
            )
        )
        for cat in cats:
            balance = await self.budget_service.get_category_balance(cat.id, month_start)
            preview.available += balance.available
        preview.future_assigned = await self._sum_assigned(ids, after=month_start)
        preview.payee_count = await self._count(
            select(Payee.id).where(
                Payee.default_category_id.in_(ids),
                Payee.is_deleted == False,  # noqa: E712
            )
        )
        preview.scheduled_count = await self._count(
            select(ScheduledTransaction.id).where(
                ScheduledTransaction.category_id.in_(ids),
                ScheduledTransaction.is_deleted == False,  # noqa: E712
            )
        )
        return preview

    async def preview_delete_group(
        self, budget_id: uuid.UUID, group_id: uuid.UUID, month: date
    ) -> CategoryDeletePreview:
        cats = await self.category_repo.get_by_group(group_id)
        return await self.preview_delete(budget_id, [c.id for c in cats], month)

    # ─── Delete ───────────────────────────────────────────────────────────────

    async def delete_categories(
        self,
        budget_id: uuid.UUID,
        category_ids: list[uuid.UUID],
        *,
        move_to: uuid.UUID | None = None,
        group_id: uuid.UUID | None = None,
        month: date | None = None,
    ) -> CategoryDeleteResult:
        """Delete categories, deciding what becomes of everything pointing at
        them. `move_to` re-files their transactions into another envelope;
        None leaves those rows genuinely uncategorized, carrying provenance.

        `month` is the month the numbers are reported for, since Ready to
        Assign is month-dependent; it should be the month the user is looking
        at, the same one the preview was taken for.
        """
        cats = await self._live_categories(budget_id, category_ids)
        if not cats:
            raise NotFoundError("Category", str(category_ids[0] if category_ids else ""))
        ids = [c.id for c in cats]

        for cat in cats:
            if reason := await self._blocking_link(cat):
                raise InvariantViolation(reason)
        await self._validate_move_target(budget_id, move_to, ids)

        as_of = first_of_month(month or date.today())
        tba_before = (await self.budget_service.get_budget_summary(budget_id, as_of)).to_be_assigned

        bookkeeping: dict[str, Any] = {}
        moved, uncategorized = await self._retarget_transactions(ids, move_to, cats, bookkeeping)
        _sum, assignments_removed = await self._clear_assignments(ids, bookkeeping)
        await self._clear_referrers(ids, bookkeeping)

        group = await self._prepare_group(group_id, ids, bookkeeping)
        for cat in cats:
            cat.is_deleted = True
        if group is not None:
            group.is_deleted = True
        await self.session.flush()

        # Measured, not derived. The money that reaches Ready to Assign is not
        # the sum of the assignment rows removed — an assignment already spent
        # against never comes back, and on the repair path the current month's
        # assignment was released when the old delete hid the category. Two
        # formulas would drift; taking the difference cannot.
        released = (
            await self.budget_service.get_budget_summary(budget_id, as_of)
        ).to_be_assigned - tba_before

        change_id = await self._record_delete(budget_id, cats, group, bookkeeping)
        return CategoryDeleteResult(
            change_id=change_id,
            category_ids=ids,
            transactions_moved=moved,
            transactions_uncategorized=uncategorized,
            assignments_removed=assignments_removed,
            released=released,
        )

    async def delete_group(
        self,
        budget_id: uuid.UUID,
        group_id: uuid.UUID,
        *,
        move_to: uuid.UUID | None = None,
        month: date | None = None,
    ) -> CategoryDeleteResult:
        """Delete a group and everything in it, as one undoable record.

        The group alone was the sharper bug: soft-deleting it left its
        categories live, so they vanished from the grid (which renders only
        groups it was given) while their balances went on reducing Ready to
        Assign — money off screen but still in the arithmetic.
        """
        group = await self.group_repo.get(group_id)
        if group is None or group.budget_id != budget_id or group.is_deleted:
            raise NotFoundError("Category group", str(group_id))
        if group.is_system:
            raise InvariantViolation("Cannot delete system category groups")
        cats = await self.category_repo.get_by_group(group_id)
        if not cats:
            return await self._delete_empty_group(budget_id, group)
        return await self.delete_categories(
            budget_id, [c.id for c in cats], move_to=move_to, group_id=group_id, month=month
        )

    # ─── Repair ───────────────────────────────────────────────────────────────

    async def repair_orphans(
        self, budget_id: uuid.UUID, month: date | None = None
    ) -> list[CategoryDeleteResult]:
        """Finish the job on categories deleted before this was a real operation.

        Deliberately an action rather than a data migration: it returns
        stranded assignment money to Ready to Assign, which is a visible change
        to the user's numbers and belongs where they can see it happen and undo
        it — not in a deploy step nobody watched.

        One record per category, so each is independently undoable, and
        idempotent: a second run finds nothing because the first cleared every
        referrer. Transactions become uncategorized rather than being guessed
        into some other envelope — the app has no basis for choosing one, and
        an uncategorized row is at least honest and findable.
        """
        dead = list(
            (
                await self.session.execute(
                    select(Category).where(
                        Category.budget_id == budget_id,
                        Category.is_deleted == True,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )

        as_of = first_of_month(month or date.today())
        results: list[CategoryDeleteResult] = []
        for cat in dead:
            tba_before = (
                await self.budget_service.get_budget_summary(budget_id, as_of)
            ).to_be_assigned
            bookkeeping: dict[str, Any] = {}
            ids = [cat.id]
            moved, uncategorized = await self._retarget_transactions(ids, None, [cat], bookkeeping)
            _sum, removed = await self._clear_assignments(ids, bookkeeping)
            await self._clear_referrers(ids, bookkeeping)
            if not (uncategorized or removed or _touched(bookkeeping)):
                continue  # already clean; nothing to record
            await self.session.flush()
            released = (
                await self.budget_service.get_budget_summary(budget_id, as_of)
            ).to_be_assigned - tba_before
            change_id = await self._record_delete(budget_id, [cat], None, bookkeeping)
            results.append(
                CategoryDeleteResult(
                    change_id=change_id,
                    category_ids=ids,
                    transactions_moved=moved,
                    transactions_uncategorized=uncategorized,
                    assignments_removed=removed,
                    released=released,
                )
            )

        # A live category under a deleted group is the other half of the class:
        # invisible on the budget page, still in the summary arithmetic. Its
        # group is what should come back, not the category that should go — so
        # this reports rather than deletes, and the caller surfaces it.
        return results

    async def count_orphaned_categories_under_deleted_groups(self, budget_id: uuid.UUID) -> int:
        return await self._count(
            select(Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(
                Category.budget_id == budget_id,
                Category.is_deleted == False,  # noqa: E712
                CategoryGroup.is_deleted == True,  # noqa: E712
            )
        )

    # ─── Steps ────────────────────────────────────────────────────────────────

    async def _retarget_transactions(
        self,
        ids: list[uuid.UUID],
        move_to: uuid.UUID | None,
        cats: list[Category],
        bookkeeping: dict[str, Any],
    ) -> tuple[int, int]:
        """Re-file or clear every row filed in these categories.

        A single bulk UPDATE rather than `TransactionService.update` per row,
        for two reasons. It is the only thing that scales to a category with a
        thousand transactions. And it deliberately includes **reconciled**
        rows: reconciliation asserts that amount, date and cleared status
        agree with the bank, which a category cannot affect — the payee-merge
        path already re-points `payee_id` on reconciled rows on the same
        reasoning. Leaving them out would strand exactly the oldest history on
        a category that no longer exists, unfixable without unreconciling.

        Split parents carry no category, so `category_id IN (…)` reaches
        leaves and split children only, which is precisely the set that
        carries category meaning.

        Provenance is stamped on **both** paths, not just the uncategorized
        one. It is what lets undo find its own rows without carrying a list of
        ids, and a moved row is otherwise indistinguishable from one that was
        already sitting in the destination — undoing would drag those along
        with it. Whether to *show* "was: Groceries" is a separate question the
        register answers from `category_id` being null.
        """
        names = {c.id: c.name for c in cats}
        # Counted before the update and over live rows only, so the number
        # reported back is the same one `preview_delete` promised. The update
        # itself deliberately has no `is_deleted` filter: a soft-deleted
        # transaction restored later must not come back pointing at a category
        # that no longer exists.
        total = await self._count(
            select(Transaction.id).where(
                Transaction.category_id.in_(ids),
                Transaction.is_deleted == False,  # noqa: E712
            )
        )
        for cat_id in ids:
            await self.session.execute(
                update(Transaction)
                .where(Transaction.category_id == cat_id)
                .values(
                    category_id=move_to,
                    prior_category_id=cat_id,
                    prior_category_name=names[cat_id],
                )
            )
        bookkeeping["_moved_to"] = str(move_to) if move_to else None
        return (total, 0) if move_to else (0, total)

    async def _clear_assignments(
        self, ids: list[uuid.UUID], bookkeeping: dict[str, Any]
    ) -> tuple[Decimal, int]:
        """Remove the categories' assignment rows, returning their money.

        `sum_after_month` sums assignments with no join to `categories`, so a
        future-month assignment on a deleted category stayed deducted from an
        earlier month's TBA while contributing to no envelope — the same
        budget reporting two different Ready to Assign figures depending on
        which month was on screen, against the invariant `get_budget_summary`
        states in its own docstring.
        """
        rows = list(
            (
                await self.session.execute(
                    select(BudgetAssignment).where(BudgetAssignment.category_id.in_(ids))
                )
            )
            .scalars()
            .all()
        )
        bookkeeping["_assignments"] = [
            {
                "id": str(r.id),
                "budget_id": str(r.budget_id),
                "category_id": str(r.category_id),
                "month": r.month.isoformat(),
                "assigned": str(r.assigned),
            }
            for r in rows
        ]
        if rows:
            await self.session.execute(
                delete(BudgetAssignment).where(BudgetAssignment.category_id.in_(ids))
            )
        return sum((r.assigned for r in rows), Decimal("0")), len(rows)

    async def _clear_referrers(self, ids: list[uuid.UUID], bookkeeping: dict[str, Any]) -> None:
        """Everything else that names these categories.

        Payee defaults and scheduled transactions are the two that kept
        *making* new orphans; view placements and filter selections are
        arrangements whose repositories filter the view's or filter's own
        `is_deleted` but never the category's.
        """
        payees = await self._ids(select(Payee.id).where(Payee.default_category_id.in_(ids)))
        bookkeeping["_payee_ids"] = [str(p) for p in payees]
        if payees:
            await self.session.execute(
                update(Payee)
                .where(Payee.default_category_id.in_(ids))
                .values(default_category_id=None)
            )

        scheduled = await self._ids(
            select(ScheduledTransaction.id).where(ScheduledTransaction.category_id.in_(ids))
        )
        bookkeeping["_scheduled_ids"] = [str(s) for s in scheduled]
        if scheduled:
            await self.session.execute(
                update(ScheduledTransaction)
                .where(ScheduledTransaction.category_id.in_(ids))
                .values(category_id=None)
            )

        placements = list(
            (
                await self.session.execute(
                    select(BudgetViewPlacement).where(BudgetViewPlacement.category_id.in_(ids))
                )
            )
            .scalars()
            .all()
        )
        bookkeeping["_placements"] = [
            {
                "view_id": str(p.view_id),
                "category_id": str(p.category_id),
                "group_id": str(p.group_id) if p.group_id else None,
                "is_hidden": bool(getattr(p, "is_hidden", False)),
            }
            for p in placements
        ]
        if placements:
            await self.session.execute(
                delete(BudgetViewPlacement).where(BudgetViewPlacement.category_id.in_(ids))
            )

        selections = list(
            (
                await self.session.execute(
                    select(BudgetFilterCategory).where(BudgetFilterCategory.category_id.in_(ids))
                )
            )
            .scalars()
            .all()
        )
        bookkeeping["_filter_selections"] = [
            {"filter_id": str(s.filter_id), "category_id": str(s.category_id)} for s in selections
        ]
        if selections:
            await self.session.execute(
                delete(BudgetFilterCategory).where(BudgetFilterCategory.category_id.in_(ids))
            )

    async def _prepare_group(
        self, group_id: uuid.UUID | None, ids: list[uuid.UUID], bookkeeping: dict[str, Any]
    ) -> CategoryGroup | None:
        if group_id is None:
            return None
        group = await self.group_repo.get(group_id)
        if group is None:
            return None
        bookkeeping["_group_id"] = str(group_id)
        bookkeeping["_group_before"] = snapshot("category_group", group)
        bookkeeping["_group_cascade"] = [str(i) for i in ids]
        return group

    async def _record_delete(
        self,
        budget_id: uuid.UUID,
        cats: list[Category],
        group: CategoryGroup | None,
        bookkeeping: dict[str, Any],
    ) -> uuid.UUID:
        """One change row for the whole operation.

        Not a batch of per-transaction changes. A batch would write a change
        row per affected transaction — a thousand rows for a well-used
        category — and the Activity page pages at fifty and groups only
        contiguous rows, so it would render as twenty pages of "Batch of 50".
        Worse, `undo_batch` is all-or-nothing with a per-row staleness check,
        so a single transaction edited afterwards would make the entire delete
        permanently un-undoable.

        The `_`-prefixed keys are undo bookkeeping, never written back onto the
        entity — the same mechanism `_undo_merge` uses for `_transaction_ids`.
        Transactions need no id list at all: `prior_category_id` names them.
        """
        primary = cats[0]
        before = snapshot("category", primary) | bookkeeping
        if len(cats) > 1 or group is not None:
            before["_categories"] = [{"id": str(c.id)} | snapshot("category", c) for c in cats]
        row = await self.changes.record(
            budget_id=budget_id,
            entity_type="category",
            entity_id=primary.id,
            action="delete",
            before=before,
        )
        await self.session.flush()
        return row.id

    async def _delete_empty_group(
        self, budget_id: uuid.UUID, group: CategoryGroup
    ) -> CategoryDeleteResult:
        before = snapshot("category_group", group)
        group.is_deleted = True
        await self.session.flush()
        row = await self.changes.record(
            budget_id=budget_id,
            entity_type="category_group",
            entity_id=group.id,
            action="delete",
            before=before,
        )
        await self.session.flush()
        return CategoryDeleteResult(
            change_id=row.id,
            category_ids=[],
            transactions_moved=0,
            transactions_uncategorized=0,
            assignments_removed=0,
            released=Decimal("0"),
        )

    # ─── Helpers ──────────────────────────────────────────────────────────────

    async def _live_categories(
        self, budget_id: uuid.UUID, category_ids: list[uuid.UUID]
    ) -> list[Category]:
        if not category_ids:
            return []
        result = await self.session.execute(
            select(Category).where(
                Category.id.in_(category_ids),
                Category.budget_id == budget_id,
                Category.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def _blocking_link(self, cat: Category) -> str | None:
        """A category the credit-card or debt machinery depends on.

        Not symmetric with account deletion, deliberately. Deleting an account
        unlinks its payment category because the account is the thing leaving
        and the category survives as an ordinary envelope. Deleting a *linked
        category* would leave a live account or liability without the envelope
        its machinery reads — `get_by_linked_account` and
        `get_by_linked_liability` both filter `is_deleted`, so it would simply
        see none. A link to an already-deleted counterpart is stale rather
        than load-bearing and does not block.
        """
        from igab.db.models import Account, Liability

        if cat.linked_account_id is not None:
            account = await self.session.get(Account, cat.linked_account_id)
            if account is not None and not account.is_deleted:
                return (
                    f"'{cat.name}' is the payment category for {account.name}. "
                    "Delete or unlink that account first."
                )
        if cat.linked_liability_id is not None:
            liability = await self.session.get(Liability, cat.linked_liability_id)
            if liability is not None and not liability.is_deleted:
                return (
                    f"'{cat.name}' is the debt category for {liability.name}. "
                    "Unlink it from that loan first."
                )
        return None

    async def _validate_move_target(
        self, budget_id: uuid.UUID, move_to: uuid.UUID | None, deleting: list[uuid.UUID]
    ) -> None:
        if move_to is None:
            return
        if move_to in deleting:
            raise InvariantViolation("Cannot move transactions into a category being deleted")
        target = await self.category_repo.get(move_to)
        if target is None or target.budget_id != budget_id:
            raise InvariantViolation("Destination category does not belong to this budget")
        # is_categorizable is served by the repo's eligibility loader — the one
        # place that decides where a transaction may be filed. A credit-card
        # payment or debt category is maintained by its transfer or its loan,
        # not by filing rows into it.
        if not target.is_categorizable:
            raise InvariantViolation(f"Transactions cannot be filed in '{target.name}'")

    async def _count(self, stmt) -> int:
        result = await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        return int(result.scalar_one())

    async def _ids(self, stmt) -> list[uuid.UUID]:
        return list((await self.session.execute(stmt)).scalars().all())

    async def _sum_assigned(self, ids: list[uuid.UUID], *, after: date) -> Decimal:
        rows = (
            await self.session.execute(
                select(BudgetAssignment.assigned).where(
                    BudgetAssignment.category_id.in_(ids),
                    BudgetAssignment.month > after,
                )
            )
        ).scalars()
        return sum((Decimal(str(r)) for r in rows), Decimal("0"))
