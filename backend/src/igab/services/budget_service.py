import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from igab.db.models import BudgetMove, Category
from igab.domain.cards import card_funding
from igab.domain.carryover import available_through, monthly_end_balances

# Aliased: `month_start` is also a local variable throughout this module
# (`month_start = first_of_month(month)`), and one name meaning two things
# is how the shadowing bug in report_service started.
from igab.domain.dates import month_end as _month_end
from igab.domain.dates import month_start as _month_start
from igab.domain.exceptions import InvariantViolation
from igab.domain.money import quantize_cents
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.snapshot_repo import SnapshotRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.change_log import ChangeRecorder, snapshot
from igab.services.ownership import require_in_budget
from igab.utils.clock import today_utc

if TYPE_CHECKING:
    from igab.repositories.budget_move_repo import BudgetMoveRepository


def _prev_month(d: date) -> date:
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def _months_back(d: date, n: int) -> list[date]:
    months = []
    cur = _prev_month(d)
    for _ in range(n):
        months.append(cur)
        cur = _prev_month(cur)
    return months


def first_of_month(d: date) -> date:
    return _month_start(d)


def last_of_month(d: date) -> date:
    return _month_end(d)


@dataclass
class CategoryBalance:
    category_id: uuid.UUID
    month: date
    assigned: Decimal
    activity: Decimal
    available: Decimal
    #: The category sits in a system (Income) group. Its `activity` is income
    #: received; its `assigned` and `available` are not envelope money —
    #: nothing can be assigned to it and nothing drains it, so `available`
    #: would only ever accumulate every dollar ever received. Decided here,
    #: where the TBA arithmetic already excludes it, and served as such: the
    #: month endpoint blanks both figures rather than letting a lifetime total
    #: sit under a hero showing what is actually free to assign.
    in_system_group: bool = False
    #: A card's set-aside envelope (Category.linked_account_id set). Its
    #: available is cash reserved for the card — in the envelope total, but
    #: not spending: excluded from total_activity (its synthetic inflows
    #: mirror spending already counted in the spending categories) and from
    #: the overspent totals (a shortfall on a card is Uncovered in the card
    #: section, not something Cover Overspent offers to fix). Decided once,
    #: here, like `in_system_group`.
    is_card_payment: bool = False


@dataclass
class CardStatus:
    """One card's row in the budget's card section (domain/cards.py).

    `balance` is the ledger balance through the viewed month (negative =
    owed). `set_aside` is the card's envelope available: funded credit
    spending + assignments − payments, floored month over month like any
    envelope. `uncovered` is what is owed beyond the set-aside — calm,
    informational, paid down by assigning to the card; a due date that
    crosses the month boundary is a normal state, not overspending."""

    account_id: uuid.UUID
    name: str
    #: None when the migration/ensure has not created it yet — the section
    #: still renders, assignment just has nowhere to land until it exists.
    category_id: uuid.UUID | None
    balance: Decimal
    set_aside: Decimal
    uncovered: Decimal


@dataclass
class CategoryHistory:
    category_id: uuid.UUID
    last_month_assigned: Decimal
    last_month_spent: Decimal
    average_assigned: Decimal
    average_spent: Decimal
    months_included: int


@dataclass
class BudgetSummary:
    to_be_assigned: Decimal
    total_assigned: Decimal
    total_activity: Decimal
    total_overspent: Decimal
    #: How many categories make up total_overspent. Counted in the same loop,
    #: over the same population, so the amount and the count cannot disagree —
    #: and both match what Cover Overspent will act on. The hero rebuilt this
    #: from the client's category list, which excludes hidden categories, so it
    #: undercounted next to an amount that included them.
    overspent_count: int
    # Dollars already committed to months after the viewed month; deducted
    # from to_be_assigned so the same dollars can't be assigned twice.
    assigned_in_future: Decimal
    category_balances: list[CategoryBalance]
    #: The budget's cards, each with balance / set aside / uncovered —
    #: computed here because their set-aside envelopes are part of the same
    #: identity Ready to Assign is. Empty when the budget has no cards.
    cards: list[CardStatus] = field(default_factory=list)


@dataclass
class FutureOverspendWarning:
    category_id: uuid.UUID
    category_name: str
    month: date
    available_before: Decimal
    available_after: Decimal


@dataclass
class CoverOverspentItem:
    category_id: uuid.UUID
    category_name: str
    overspent: Decimal
    proposed_addition: Decimal
    remaining_after: Decimal


@dataclass
class CoverOverspentPreview:
    items: list[CoverOverspentItem]
    total_overspent: Decimal
    total_addition: Decimal
    tba_before: Decimal
    tba_after: Decimal


def distribute_cover(
    shortfalls: dict[uuid.UUID, Decimal],
    available_tba: Decimal,
) -> dict[uuid.UUID, Decimal]:
    """Distribute TBA across overspent categories, proportionally when short.

    When TBA covers the total shortfall, every category is covered in full.
    When short, each category gets its proportional share rounded DOWN to
    cents — unlike fill-targets' half-even rounding, this guarantees the sum
    never exceeds TBA (apply hard-rejects overshoot, so a preview must never
    propose one). Leftover cents stay in TBA.
    """
    available_tba = max(Decimal("0"), available_tba)
    total_shortfall = sum(shortfalls.values(), Decimal("0"))
    result: dict[uuid.UUID, Decimal] = {}
    for cat_id, needed in shortfalls.items():
        if total_shortfall <= 0 or available_tba <= 0:
            proposed = Decimal("0")
        elif total_shortfall <= available_tba:
            proposed = needed
        else:
            # Multiply before dividing: needed/total loses exactness (1/3 ...),
            # and rounding an exact share like 100.00 down to 99.99 leaks cents.
            share = needed * available_tba / total_shortfall
            proposed = min(needed, share.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        result[cat_id] = proposed
    return result


class BudgetService:
    def __init__(
        self,
        account_repo: AccountRepository,
        category_repo: CategoryRepository,
        category_group_repo: CategoryGroupRepository,
        assignment_repo: BudgetAssignmentRepository,
        transaction_repo: TransactionRepository,
        move_repo: "BudgetMoveRepository | None" = None,
        snapshot_repo: SnapshotRepository | None = None,
    ) -> None:
        self.account_repo = account_repo
        self.category_repo = category_repo
        self.category_group_repo = category_group_repo
        self.assignment_repo = assignment_repo
        self.transaction_repo = transaction_repo
        self.move_repo = move_repo
        self.snapshot_repo = snapshot_repo
        self.changes = ChangeRecorder(assignment_repo.session)

    async def _record_assignment(
        self, assignment, before_assigned: Decimal, move: BudgetMove | None = None
    ) -> None:
        """Record an assignment change (all assignment writes are updates —
        get_or_create means the row may be fresh, in which case before is 0).

        `move` ties the row to the budget move that produced it: undoing the
        move finds its rows by it, undoing the row deletes the move, and redo
        recreates it.
        Underscore keys are bookkeeping — snapshot matching and field restore
        both skip them."""
        after = snapshot("assignment", assignment)
        if move is not None:
            after["_move_id"] = str(move.id)
            # Enough to recreate the audit row on redo, under the same id
            after["_move"] = {
                "month": move.month.isoformat(),
                "from_category_id": str(move.from_category_id) if move.from_category_id else None,
                "to_category_id": str(move.to_category_id) if move.to_category_id else None,
                "amount": str(move.amount),
            }
        await self.changes.record(
            budget_id=assignment.budget_id,
            entity_type="assignment",
            entity_id=assignment.id,
            action="update",
            before={
                "category_id": str(assignment.category_id),
                "month": assignment.month.isoformat(),
                "assigned": str(before_assigned),
            },
            after=after,
        )

    async def _require_envelope(self, budget_id: uuid.UUID, category_id: uuid.UUID) -> None:
        """Refuse to put money into, or take it out of, an income category.

        A category in a system group is where income is *filed*, not an
        envelope: money assigned there would neither reduce To Be Assigned nor
        ever come back out. The pickers already hide such categories
        (`is_assignable`); this is the same rule where the money actually moves.
        """
        category = await self.category_repo.get(category_id)
        if category is None or str(category.budget_id) != str(budget_id):
            raise InvariantViolation("Category does not belong to this budget")
        group = await self.category_group_repo.get(category.category_group_id)
        if group is not None and group.is_system:
            raise InvariantViolation("Income categories do not hold money")

    async def get_category_balance(
        self,
        category_id: uuid.UUID,
        month: date,
        activity_by_month: dict[date, Decimal] | None = None,
    ) -> CategoryBalance:
        """
        Compute available balance for a category through the given month.

        Replicates YNAB's overspending-coverage behavior: when a category ends a
        month negative (cash overspent), that negative amount is covered from TBA
        and the carryover into the next month is floored at zero.
        """
        month_start = first_of_month(month)

        assignments = await self.assignment_repo.get_for_category(
            category_id, through_month=month_start
        )
        this_assigned = next(
            (a.assigned for a in assignments if a.month == month_start), Decimal("0")
        )

        if activity_by_month is None:
            activity_by_month = await self.transaction_repo.sum_by_category_by_month(
                category_id, end_date=last_of_month(month_start)
            )

        this_activity = activity_by_month.get(month_start, Decimal("0"))

        available = available_through(
            {a.month: a.assigned for a in assignments}, activity_by_month, month_start
        )

        return CategoryBalance(
            category_id=category_id,
            month=month_start,
            assigned=this_assigned,
            activity=this_activity,
            available=available,
        )

    async def get_budget_summary(self, budget_id: uuid.UUID, month: date) -> BudgetSummary:
        """
        Compute TBA and all category balances for a given month.

        TBA = sum(cash account balances through the month's end)
              - sum(envelope category balances through the month,
                    cards' set-aside envelopes included)
              - sum(assignments in months after the viewed month)
              - the credit-funded part of the viewed month's overspending
                (already riding on cards, not yet written off — see
                domain/cards.py)

        Cards are outside the cash term: a card's debt lives beside its
        set-aside in the cards section, and the only way a card moves this
        figure is money assigned to it.

        The future-assignment deduction is YNAB's rule: assigning $500 in
        September must reduce August's TBA too, or the same dollars could be
        assigned twice. With it, a budget whose only allocation is that $500
        shows the same TBA whether August or September is on screen — but
        only while the later months' spending is funded by money already on
        hand, because the balance term is month-bounded while the deduction
        is not (future income raises only its own month). The test that pins
        this carries the qualifier in its name:
        `test_ready_to_assign_agrees_across_months_when_next_months_spending_is_covered`.
        The balance term is bounded the same way the activity term is, and
        includes closed accounts — see
        `AccountRepository.sum_on_budget_balance` for both reasons.
        """
        month_start = first_of_month(month)

        total_account_balance = await self.account_repo.sum_on_budget_balance(
            budget_id, last_of_month(month_start)
        )

        # All category balances
        categories = await self.category_repo.get_all(budget_id, include_hidden=True)
        groups = await self.category_group_repo.get_all(budget_id, include_hidden=True)
        system_group_ids = {g.id for g in groups if g.is_system}

        if self.snapshot_repo is not None:
            balance_map = await self._snapshot_balances(budget_id, categories, month_start)
        else:
            # Live path: batch per-month activity in one query, then simulate
            # each category. Kept as the no-snapshot fallback and the test
            # oracle the snapshot path is verified against.
            all_activity_by_month = await self.transaction_repo.sum_all_categories_by_month(
                [cat.id for cat in categories], end_date=last_of_month(month_start)
            )
            balance_map = {
                cat.id: await self.get_category_balance(
                    cat.id, month_start, activity_by_month=all_activity_by_month.get(cat.id, {})
                )
                for cat in categories
            }

        # ── Cards (domain/cards.py). Each card's set-aside is an envelope
        # simulated over synthetic activity: funded credit spending flows in,
        # payments flow out, assignments on the linked category add to it.
        # The credit-funded part of the viewed month's overspending has not
        # been written off yet — the category still shows red — so it comes
        # out of Ready to Assign directly (`uncovered_current`; the YNAB
        # oracle states the same rule over an export).
        zero = Decimal("0")
        cards: list[CardStatus] = []
        uncovered_current = zero
        card_accounts = [
            a
            for a in await self.account_repo.get_all(budget_id, include_closed=True)
            if a.on_budget and a.classification == "liability"
        ]
        if card_accounts:
            month_end_date = last_of_month(month_start)
            linked_by_account = {
                cat.linked_account_id: cat for cat in categories if cat.linked_account_id
            }
            spending_ids = [
                c.id
                for c in categories
                if c.linked_account_id is None and c.category_group_id not in system_group_ids
            ]
            spending_activity = await self.transaction_repo.sum_all_categories_by_month(
                spending_ids, end_date=month_end_date
            )
            assignments_by_cat: dict[uuid.UUID, dict[date, Decimal]] = {}
            for a in await self.assignment_repo.get_all_for_budget(budget_id):
                if a.month <= month_start:
                    assignments_by_cat.setdefault(a.category_id, {})[a.month] = a.assigned
            end_balances = {
                cid: monthly_end_balances(
                    assignments_by_cat.get(cid, {}), spending_activity.get(cid, {})
                )
                for cid in spending_ids
            }
            credit_outflows = await self.transaction_repo.sum_credit_outflows_by_category(
                spending_ids, month_end_date
            )
            funded_by_card, floored_by_category = card_funding(end_balances, credit_outflows)
            payments = await self.transaction_repo.sum_card_payments_by_month(
                budget_id, month_end_date
            )
            owed_by_card = await self.account_repo.card_balances(budget_id, month_end_date)
            for account in card_accounts:
                linked = linked_by_account.get(account.id)
                synthetic = dict(funded_by_card.get(account.id, {}))
                for m, paid in payments.get(account.id, {}).items():
                    synthetic[m] = synthetic.get(m, zero) - paid
                card_assignments = assignments_by_cat.get(linked.id, {}) if linked else {}
                set_aside = available_through(card_assignments, synthetic, month_start)
                if linked is not None:
                    # The linked category's balance is this computation, not
                    # the transaction sums — nothing can be filed there, and
                    # its snapshot rows (assignments only) are ignored.
                    balance_map[linked.id] = CategoryBalance(
                        category_id=linked.id,
                        month=month_start,
                        assigned=card_assignments.get(month_start, zero),
                        activity=synthetic.get(month_start, zero),
                        available=set_aside,
                        is_card_payment=True,
                    )
                balance = owed_by_card.get(account.id, zero)
                cards.append(
                    CardStatus(
                        account_id=account.id,
                        name=account.name,
                        category_id=linked.id if linked else None,
                        balance=balance,
                        set_aside=set_aside,
                        # Owed beyond the reserve. An overpaid-in-month
                        # envelope (negative set-aside) reserves nothing, so
                        # it is floored before subtracting.
                        uncovered=max(zero, -balance - max(zero, set_aside)),
                    )
                )
            uncovered_current = sum(
                (by_month.get(month_start, zero) for by_month in floored_by_category.values()),
                zero,
            )

        balances: list[CategoryBalance] = []
        total_category_balance = Decimal("0")
        total_assigned = Decimal("0")
        total_activity = Decimal("0")
        total_overspent = Decimal("0")
        overspent_count = 0

        for cat in categories:
            bal = balance_map[cat.id]
            # Decided once, here, and carried on the row: every consumer —
            # the month endpoint, Cover Overspent, the Guide's checkup — reads
            # the flag rather than re-deriving which groups are system.
            bal.in_system_group = cat.category_group_id in system_group_ids
            bal.is_card_payment = cat.linked_account_id is not None
            balances.append(bal)
            # Exclude system (Income) categories: income adds to TBA, not
            # reduces it — and it is not envelope money, so the month's
            # envelope totals leave it out as well. Hidden categories stay in:
            # they still hold money and still overspend. (This is not
            # `is_assignable`, which answers what a picker may *offer*.)
            if bal.in_system_group:
                continue
            total_category_balance += bal.available
            total_assigned += bal.assigned
            if bal.is_card_payment:
                # In the envelope total (reserved cash is not assignable) and
                # in assigned (a real allocation), but not spending and not
                # overspending — see the flag's comment.
                continue
            if bal.available < 0:
                total_overspent += -bal.available
                overspent_count += 1
            total_activity += bal.activity

        assigned_in_future = await self.assignment_repo.sum_after_month(budget_id, month_start)
        to_be_assigned = (
            total_account_balance - total_category_balance - assigned_in_future - uncovered_current
        )

        return BudgetSummary(
            to_be_assigned=to_be_assigned,
            total_assigned=total_assigned,
            total_activity=total_activity,
            total_overspent=total_overspent,
            overspent_count=overspent_count,
            assigned_in_future=assigned_in_future,
            category_balances=balances,
            cards=cards,
        )

    async def _snapshot_balances(
        self,
        budget_id: uuid.UUID,
        categories: list[Category],
        month_start: date,
    ) -> dict[uuid.UUID, CategoryBalance]:
        """Category balances served from the snapshot cache, rebuilding it first
        if any relevant write invalidated it (see igab.db.invalidation)."""
        assert self.snapshot_repo is not None
        if not await self.snapshot_repo.is_valid(budget_id):
            await self._rebuild_snapshots(budget_id, categories)

        latest = await self.snapshot_repo.latest_per_category(budget_id, month_start)
        zero = Decimal("0")
        out: dict[uuid.UUID, CategoryBalance] = {}
        for cat in categories:
            row = latest.get(cat.id)
            if row is None:
                assigned, activity, available = zero, zero, zero
            elif row.month == month_start:
                # The viewed month has its own data; available may be negative.
                assigned, activity, available = row.assigned, row.activity, row.available
            else:
                # No data in the viewed month: available is the floored
                # carryover — overspending was already absorbed by TBA.
                assigned, activity, available = zero, zero, max(zero, row.available)
            out[cat.id] = CategoryBalance(
                category_id=cat.id,
                month=month_start,
                assigned=assigned,
                activity=activity,
                available=available,
            )
        return out

    async def _rebuild_snapshots(self, budget_id: uuid.UUID, categories: list[Category]) -> None:
        """Recompute every (category, month) row from source data.

        Two batched queries replace the per-category fetches of the live path;
        the simulation itself must mirror get_category_balance exactly.
        """
        assert self.snapshot_repo is not None
        zero = Decimal("0")

        # No end_date: snapshots must cover future-dated activity too, so any
        # month can be served. Forward simulation means later months never
        # affect earlier rows.
        activity = await self.transaction_repo.sum_all_categories_by_month(
            [cat.id for cat in categories]
        )
        assignments = await self.assignment_repo.get_all_for_budget(budget_id)
        assigned_by_cat: dict[uuid.UUID, dict[date, Decimal]] = {}
        for a in assignments:
            assigned_by_cat.setdefault(a.category_id, {})[a.month] = a.assigned

        rows: list[dict[str, object]] = []
        for cat in categories:
            asg = assigned_by_cat.get(cat.id, {})
            act = activity.get(cat.id, {})
            # One loop, the domain's: these rows must be exactly what
            # `available_through` would say, month by month.
            for m, end_of_month in monthly_end_balances(asg, act).items():
                rows.append(
                    {
                        "budget_id": budget_id,
                        "category_id": cat.id,
                        "month": m,
                        "assigned": asg.get(m, zero),
                        "activity": act.get(m, zero),
                        "available": end_of_month,
                    }
                )

        await self.snapshot_repo.replace_for_budget(budget_id, rows)

    async def preview_future_overspend(
        self,
        budget_id: uuid.UUID,
        items: list[tuple[uuid.UUID, date, Decimal]],
    ) -> list[FutureOverspendWarning]:
        """Which categories would a pending edit push negative in a *future* month?

        Each item is (category_id, transaction date, signed amount delta —
        outflow negative). Only months after the current month are checked:
        current-month overspending is already visible on the budget page, but a
        future month's negative sits unseen until the user navigates there, so
        the caller warns before saving. Items landing in the same category and
        month are summed first (splits; edit reversals), and categories outside
        this budget are ignored rather than leaked.
        """
        current_month = first_of_month(today_utc())
        deltas: dict[tuple[uuid.UUID, date], Decimal] = {}
        for category_id, txn_date, delta in items:
            month = first_of_month(txn_date)
            if month <= current_month:
                continue
            key = (category_id, month)
            deltas[key] = deltas.get(key, Decimal("0")) + delta

        if not deltas:
            return []

        categories = await self.category_repo.get_all(budget_id, include_hidden=True)
        name_by_id = {c.id: c.name for c in categories}

        warnings: list[FutureOverspendWarning] = []
        for (category_id, month), delta in sorted(
            deltas.items(), key=lambda kv: (kv[0][1], str(kv[0][0]))
        ):
            if delta >= 0 or category_id not in name_by_id:
                continue
            bal = await self.get_category_balance(category_id, month)
            after = bal.available + delta
            if after < 0:
                warnings.append(
                    FutureOverspendWarning(
                        category_id=category_id,
                        category_name=name_by_id[category_id],
                        month=month,
                        available_before=bal.available,
                        available_after=after,
                    )
                )
        return warnings

    async def set_assignment(
        self,
        budget_id: uuid.UUID,
        category_id: uuid.UUID,
        month: date,
        amount: Decimal,
    ) -> None:
        await self._require_envelope(budget_id, category_id)
        month_start = first_of_month(month)
        assignment = await self.assignment_repo.get_or_create(
            budget_id=budget_id,
            category_id=category_id,
            month=month_start,
        )
        before_assigned = assignment.assigned
        updated = await self.assignment_repo.update(assignment.id, assigned=amount)
        if updated.assigned != before_assigned:
            await self._record_assignment(updated, before_assigned)

    async def get_category_history(
        self,
        budget_id: uuid.UUID,
        category_id: uuid.UUID,
        current_month: date,
        lookback: int = 6,
    ) -> "CategoryHistory":
        # Guard: category_id may arrive from a request body (batch history),
        # bypassing the route's BudgetAccess check. Reject foreign categories
        # so history cannot be read across budgets.
        await require_in_budget(
            self.category_repo.session, Category, category_id, budget_id, "Category"
        )
        month_start = first_of_month(current_month)
        past_months = _months_back(month_start, lookback)

        assignments = await self.assignment_repo.get_for_category(category_id)
        assigned_by_month = {a.month: a.assigned for a in assignments}

        # Activity through the most RECENT past month (past_months[0]); the
        # current month's spending must not leak into history.
        activity_by_month = await self.transaction_repo.sum_by_category_by_month(
            category_id, end_date=last_of_month(past_months[0] if past_months else month_start)
        )
        # activity is negative for spending; flip sign for "spent" values
        spent_by_month = {m: -v for m, v in activity_by_month.items() if v < 0}

        last_month = past_months[0] if past_months else None
        last_assigned = (
            assigned_by_month.get(last_month, Decimal("0")) if last_month else Decimal("0")
        )
        last_spent = spent_by_month.get(last_month, Decimal("0")) if last_month else Decimal("0")

        months_with_data = [m for m in past_months if m in assigned_by_month or m in spent_by_month]
        n = len(months_with_data) if months_with_data else 1
        zero = Decimal("0")
        avg_assigned = sum((assigned_by_month.get(m, zero) for m in past_months), zero) / n
        avg_spent = sum((spent_by_month.get(m, zero) for m in past_months), zero) / n

        return CategoryHistory(
            category_id=category_id,
            last_month_assigned=last_assigned,
            last_month_spent=last_spent,
            average_assigned=quantize_cents(avg_assigned),
            average_spent=quantize_cents(avg_spent),
            months_included=n,
        )

    async def auto_assign(
        self,
        budget_id: uuid.UUID,
        category_id: uuid.UUID,
        month: date,
        action: str,
    ) -> None:
        history = await self.get_category_history(budget_id, category_id, month)
        amount_map = {
            "last_month_assigned": history.last_month_assigned,
            "last_month_spent": history.last_month_spent,
            "average_assigned": history.average_assigned,
            "average_spent": history.average_spent,
            "reset": Decimal("0"),
        }
        amount = amount_map.get(action, Decimal("0"))
        await self.set_assignment(budget_id, category_id, month, amount)

    async def move_money(
        self,
        budget_id: uuid.UUID,
        from_category_id: uuid.UUID | None,
        to_category_id: uuid.UUID | None,
        amount: Decimal,
        month: date,
    ) -> None:
        """Move funds between envelopes by adjusting assignments.

        A NULL side means To-Be-Assigned: from=None pulls money out of TBA
        into a category; to=None releases a category's money back to TBA.
        The move is recorded in the budget_moves audit trail.
        """
        if amount <= 0:
            raise InvariantViolation("Amount to move must be positive")
        if from_category_id == to_category_id:
            raise InvariantViolation("Choose two different envelopes")

        month_start = first_of_month(month)

        for category_id in (from_category_id, to_category_id):
            if category_id is not None:
                await self._require_envelope(budget_id, category_id)

        # The audit row first, so both assignment change rows can carry its id.
        move = None
        if self.move_repo is not None:
            move = await self.move_repo.create(
                budget_id=budget_id,
                month=month_start,
                from_category_id=from_category_id,
                to_category_id=to_category_id,
                amount=amount,
            )

        with self.changes.batch():
            if from_category_id is not None:
                from_assignment = await self.assignment_repo.get_or_create(
                    budget_id, from_category_id, month_start
                )
                before_from = from_assignment.assigned
                updated_from = await self.assignment_repo.update(
                    from_assignment.id, assigned=from_assignment.assigned - amount
                )
                await self._record_assignment(updated_from, before_from, move)
            if to_category_id is not None:
                to_assignment = await self.assignment_repo.get_or_create(
                    budget_id, to_category_id, month_start
                )
                before_to = to_assignment.assigned
                updated_to = await self.assignment_repo.update(
                    to_assignment.id, assigned=to_assignment.assigned + amount
                )
                await self._record_assignment(updated_to, before_to, move)
        # The rows must be queryable by the next statement in this transaction
        # (undo_move, a batch undo): a session without autoflush would otherwise
        # hold the last-recorded side back until something else flushed.
        await self.changes.session.flush()

    async def get_move_history(self, budget_id: uuid.UUID, month: date):
        if self.move_repo is None:
            return []
        return await self.move_repo.get_for_month(budget_id, first_of_month(month))

    async def _overspent_shortfalls(
        self, budget_id: uuid.UUID, month: date
    ) -> tuple["BudgetSummary", dict[uuid.UUID, Decimal]]:
        """Current summary plus {category_id: overspent amount} for envelope
        categories. Hidden categories are included on purpose — they participate
        in the TBA math, so covering them is required to zero out overspending."""
        summary = await self.get_budget_summary(budget_id, month)
        shortfalls = {
            b.category_id: -b.available
            for b in summary.category_balances
            if b.available < 0 and not b.in_system_group and not b.is_card_payment
        }
        return summary, shortfalls

    async def cover_overspent_preview(
        self, budget_id: uuid.UUID, month: date
    ) -> CoverOverspentPreview:
        summary, shortfalls = await self._overspent_shortfalls(budget_id, month)
        proposed = distribute_cover(shortfalls, summary.to_be_assigned)

        categories = await self.category_repo.get_all(budget_id, include_hidden=True)
        name_map = {c.id: c.name for c in categories}

        items = [
            CoverOverspentItem(
                category_id=cat_id,
                category_name=name_map.get(cat_id, "Unknown"),
                overspent=shortfall,
                proposed_addition=proposed[cat_id],
                remaining_after=shortfall - proposed[cat_id],
            )
            for cat_id, shortfall in shortfalls.items()
        ]
        items.sort(key=lambda i: (-i.proposed_addition, str(i.category_id)))
        total_addition = sum((i.proposed_addition for i in items), Decimal("0"))

        return CoverOverspentPreview(
            items=items,
            total_overspent=summary.total_overspent,
            total_addition=total_addition,
            tba_before=summary.to_be_assigned,
            tba_after=summary.to_be_assigned - total_addition,
        )

    async def cover_overspent_apply(
        self,
        budget_id: uuid.UUID,
        month: date,
        items: list[tuple[uuid.UUID, Decimal]],
    ) -> None:
        """Apply a cover-overspent preview by moving money from TBA.

        Re-validates against fresh balances so a stale preview (transactions or
        assignments changed since it was fetched) cannot over-assign: each
        addition is capped by the category's current shortfall and the total by
        current TBA. Each cover routes through move_money, so it lands in the
        budget_moves audit trail as "TBA → category".
        """
        summary, shortfalls = await self._overspent_shortfalls(budget_id, month)
        available_tba = max(Decimal("0"), summary.to_be_assigned)

        to_apply = [(cat_id, amount) for cat_id, amount in items if amount > 0]
        total = sum((amount for _, amount in to_apply), Decimal("0"))
        if total > available_tba:
            raise InvariantViolation(
                "Cover amount exceeds Ready to Assign — refresh the preview and try again"
            )
        for cat_id, amount in to_apply:
            shortfall = shortfalls.get(cat_id, Decimal("0"))
            if amount > shortfall:
                raise InvariantViolation(
                    "Cover amount exceeds current overspending — refresh the preview and try again"
                )

        with self.changes.batch() as batch_id:
            for cat_id, amount in to_apply:
                await self.move_money(budget_id, None, cat_id, amount, month)
        return batch_id if to_apply else None
