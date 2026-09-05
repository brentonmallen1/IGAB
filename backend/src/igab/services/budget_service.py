import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from igab.db.models import BudgetMove, Category
from igab.domain.cards import (
    CardFunding,
    CardReserve,
    card_funding,
    card_position,
    card_reserve,
    reserve_discrepancy,
)
from igab.domain.carryover import (
    available_at,
    available_through,
    monthly_end_balances,
    sum_through,
)

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
from igab.repositories.import_anchor_repo import (
    BudgetAnchor,
    ImportAnchorRepository,
    category_opening,
)
from igab.repositories.snapshot_repo import SnapshotRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.change_log import ChangeRecorder, snapshot
from igab.services.ownership import require_in_budget
from igab.utils.clock import today_utc

if TYPE_CHECKING:
    from igab.domain.card_timeline import Breach as TimelineBreach
    from igab.domain.card_timeline import CardMonth as TimelineMonth
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
    #: The part of THIS MONTH's card inflows filed here that repaid uncovered
    #: debt rather than returning money to this envelope — money that reduced
    #: what the card owes while no cash arrived, so the envelope cannot spend
    #: it (domain/cards.py `release_split`).
    #:
    #: Already inside `available`: it is an adjustment to the month's activity
    #: made *inside* the carryover walk, not a deduction applied after it.
    #: Carried so the row can say why its activity differs from the register's.
    #:
    #: **Never a running total.** Its predecessor summed every such inflow
    #: since inception and subtracted that from a floored carryover balance —
    #: two series that are not commensurable — and grew to roughly 31x its
    #: first year's value on a real budget, all of it rendered as overspending
    #: ("The Refused Repayment").
    repaid_uncovered_debt: Decimal = Decimal("0")
    #: A card's set-aside envelope (Category.linked_account_id set). Its
    #: available is cash reserved for the card — in the envelope total, but
    #: not spending: excluded from total_activity (its synthetic inflows
    #: mirror spending already counted in the spending categories) and from
    #: the overspent totals (a shortfall on a card is Uncovered in the card
    #: section, not something Cover Overspent offers to fix). Decided once,
    #: here, like `in_system_group`.
    is_card_payment: bool = False
    #: The part of this month's shortfall that was spent on a card, straight
    #: out of `card_funding`'s `floored_by_category` — the same dict
    #: `uncovered_current` is summed from, so a row and the Ready to Assign
    #: arithmetic cannot tell different stories about the same dollars.
    #:
    #: It is the answer to "does this red cost me anything": it does not.
    #: Filing a card charge moves Ready to Assign by exactly zero — the
    #: covered part raises the card's set-aside (itself in the envelope
    #: total), the rest is subtracted here as `uncovered_current`, and the
    #: envelope's own fall raises the figure by the whole charge. At the
    #: month boundary this part rides onto the card as Uncovered instead of
    #: being written off. Only `available + credit_overspent` — the cash
    #: part — ever charges Ready to Assign.
    credit_overspent: Decimal = Decimal("0")


@dataclass
class CardStatus:
    """One card's row in the budget's card section (domain/cards.py).

    `balance` is the ledger balance through the viewed month (negative =
    owed). `set_aside` is the card's envelope available: funded credit
    spending + assignments − payments, carried as a running total
    (domain/cards.py `CardReserve`). `uncovered` is what is owed
    beyond the set-aside — calm, informational, paid down by assigning to
    the card; a due date that crosses the month boundary is a normal state,
    not overspending.

    A closed card keeps its row while it has something to say — a residual
    balance, a reserve someone can still move money out of — and carries
    `is_closed` so the section can tag it. A closed card with all three at
    zero is settled and gets no row at all (`get_budget_summary` skips it
    after the arithmetic): the sums it feeds are unchanged — closing moves
    no money — but a permanently undismissable zero row is display, and
    display is a different question from arithmetic."""

    account_id: uuid.UUID
    name: str
    #: None when the migration/ensure has not created it yet — the section
    #: still renders, assignment just has nowhere to land until it exists.
    category_id: uuid.UUID | None
    balance: Decimal
    set_aside: Decimal
    uncovered: Decimal
    is_closed: bool
    #: How much of *this month's* overspending was swiped on this card and is
    #: riding here rather than charging Ready to Assign. Part of `uncovered`
    #: already — this names which card carries it, which only becomes a real
    #: question with more than one, because they are paid separately.
    overspent_this_month: Decimal = Decimal("0")
    #: 0 when this card's reserve identity holds with all three of its bounds
    #: met, otherwise the amount by which one does not
    #: (domain/cards.py `reserve_discrepancy`). Served rather than re-derived
    #: so the integrity check reads the same arithmetic the budget page does.
    #: Every defect this model has had was visible in this one number, and the
    #: invariant that would have caught them was excused for exactly the
    #: histories that produce them.
    reserve_discrepancy: Decimal = Decimal("0")
    #: The five legs `set_aside` is the running total of, each summed through
    #: the viewed month, plus what is still riding uncovered on the card.
    #:
    #:     assigned + reserved − released − residual − payments == set_aside
    #:
    #: Served because every question this model has raised was answered by
    #: decomposing one number into the flows that produced it, and the surface
    #: showed only the total. The client renders them; it must not sum them —
    #: `set_aside` is already served, and a second opinion about what a
    #: reserve is is exactly what "Two Ledgers, One Debt" was.
    assigned: Decimal = Decimal("0")
    reserved: Decimal = Decimal("0")
    released: Decimal = Decimal("0")
    residual: Decimal = Decimal("0")
    payments: Decimal = Decimal("0")
    #: The sixth leg, first in time: YNAB's own CCP Available at an import
    #: anchor's B−1. Zero everywhere but anchored budgets. With it the legs
    #: still sum to `set_aside` — `opening + assigned + reserved − released −
    #: residual − payments` — and the other five stay post-anchor sums.
    opening: Decimal = Decimal("0")
    #: What is riding uncovered on this card, lifetime — what went on, less
    #: what an inflow discharged, less what an assignment covered. Distinct
    #: from `uncovered`, which is what the card OWES beyond its reserve.
    riding: Decimal = Decimal("0")
    #: The rest of `card_position`, beside `uncovered` above. A zero
    #: `reserve_discrepancy` means the identity's BOUNDS hold, not that the
    #: reserve is anywhere near the balance — the bounds are allowances, and
    #: they excuse both of the shapes a real budget produced: a reserve
    #: several times its balance (assignments that never had a ride to retire)
    #: and a reserve below zero on a card still owing thousands (years of
    #: residual). Both reported nothing. These say WHICH way a card is
    #: unusual, so the row can explain itself where the check is silent.
    over_reserved: Decimal = Decimal("0")
    short_reserved: Decimal = Decimal("0")
    #: The card owes nothing and holds your money — the only state the word
    #: "overpaid" was ever true of. `short_reserved` alone is not it.
    card_credit: Decimal = Decimal("0")
    #: This month, from the card's own ledger rather than the reserve's legs.
    #: `paid_this_month` is paired transfers from cash (the `payments` leg's
    #: own month); `debt_change_this_month` is the net move of the BALANCE,
    #: every row included. They differ by refunds, interest, and payments
    #: whose transfer leg was never paired — a gap worth showing, not hiding.
    charged_this_month: Decimal = Decimal("0")
    #: EVERY credit the card's ledger took this month — refunds, rewards,
    #: somebody else paying the bill, and payments whose transfer leg was
    #: never paired — where `paid_this_month` is paired transfers from cash
    #: only. The gap between the two is the diagnostic
    #: (`card_month_flows`' own words), and the client used to reconstruct
    #: it as `debt_change + charged − paid` — a plug that cannot fail to
    #: reconcile, so it silently absorbed any error in the other terms and
    #: relabelled it "other credits". Served, so the month block renders
    #: figures and never sums them.
    inflows_this_month: Decimal = Decimal("0")
    paid_this_month: Decimal = Decimal("0")
    #: Signed: positive means the debt shrank this month.
    debt_change_this_month: Decimal = Decimal("0")
    #: Signed net of this month's rows the bank still calls pending, which
    #: `POSTED` keeps out of all three figures above AND out of `balance`. The
    #: panel and the balance therefore agree with each other and disagree with
    #: the register by exactly this. Served so the surface can say so: a card
    #: whose register the user counted did not match the panel, and nothing on
    #: screen accounted for the difference.
    pending_this_month: Decimal = Decimal("0")
    #: Which months put riding debt on this card, and how much. The remedy
    #: needs the month: funding an envelope in the month it ended short
    #: retires the ride (the walk is recomputed from scratch every request),
    #: while funding it the following month does not reach back.
    #: `overspent_this_month` above is this series' entry for the viewed
    #: month, not a second computation.
    #:
    #: **Gross, and `riding` is net.** These are the months debt went ON;
    #: an assignment that later retired some of it is recorded against the
    #: month of the ASSIGNMENT (`covered_by_card`), not against the month
    #: that rode, so there is no month attribution for what remains. The two
    #: therefore disagree once anything has been covered, and the surface has
    #: to say so rather than point at a month that is already settled.
    #: Chronological here; the surface orders and caps for display.
    rode_by_month: list[tuple[date, Decimal]] = field(default_factory=list)


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
    #: `total_overspent` split by what funds it. Credit overspending rode onto
    #: a card and is already reflected in Uncovered; it never charges Ready to
    #: Assign, this month or at the boundary. Cash overspending is written off
    #: from Ready to Assign when the month rolls. The headline stays whole —
    #: the red on the grid is real either way — but every figure that implies
    #: an action reads the cash one, because that is the only part an action
    #: can change. The glossary promised this before the code did.
    total_overspent_cash: Decimal
    total_overspent_credit: Decimal
    #: How many categories carry a cash shortfall — what Cover Overspent lists.
    #: Counted in the same loop as the amount, for the reason above.
    overspent_count_cash: int
    # Dollars already committed to months after the viewed month; deducted
    # from to_be_assigned so the same dollars can't be assigned twice.
    assigned_in_future: Decimal
    category_balances: list[CategoryBalance]
    #: The budget's cards, each with balance / set aside / uncovered —
    #: computed here because their set-aside envelopes are part of the same
    #: identity Ready to Assign is. Empty when the budget has no cards.
    cards: list[CardStatus] = field(default_factory=list)
    #: B, the first month this budget's envelope math re-derives — set only
    #: on budgets anchored at import (repositories/import_anchor_repo.py).
    #: The client clamps month navigation here; months before it live in the
    #: register and reports only.
    anchor_month: date | None = None


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
    #: What `items` sums to before any distribution — the cash shortfall, which
    #: is the whole of what this dialog can act on.
    total_overspent: Decimal
    #: Overspending left out of `items` because it rode onto a card. Shown so
    #: the difference between this dialog and the grid's red is stated rather
    #: than left for the reader to notice and distrust.
    total_overspent_credit: Decimal
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


@dataclass(frozen=True)
class CardWalk:
    """One assembly of the card model's inputs (`BudgetService.card_walk`).

    A dataclass, not a tuple: the tuple grew its fifth slot with every caller
    unpacking placeholders, which is how an unnamed slot ships untested.
    `credit_outflows` is carried so attribution surfaces (hygiene, the
    timeline) can say which categories charged which card without re-running
    the repository query the walk was built from.
    """

    card_accounts: list = field(default_factory=list)
    linked_by_account: dict[uuid.UUID, Category] = field(default_factory=dict)
    funding: CardFunding[uuid.UUID, uuid.UUID] = field(default_factory=CardFunding)
    payments: dict[uuid.UUID, dict[date, Decimal]] = field(default_factory=dict)
    unclaimed: dict[uuid.UUID, dict[date, Decimal]] = field(default_factory=dict)
    #: {category: {card: {month: SIGNED net}}} — the walk's own input, kept.
    credit_outflows: dict[uuid.UUID, dict[uuid.UUID, dict[date, Decimal]]] = field(
        default_factory=dict
    )
    #: The budget's import anchor, loaded once here so hygiene, the timeline
    #: and the parity check read the same seeds the walk consumed. None on
    #: every unanchored budget — the byte-identical path.
    anchor: BudgetAnchor | None = None


def _from_month(
    series_by_key: dict[uuid.UUID, dict[date, Decimal]], start: date
) -> dict[uuid.UUID, dict[date, Decimal]]:
    """Each key's monthly series with months before `start` dropped —
    the anchor's truncation, applied to repository sums the walk never sees."""
    return {
        key: {m: v for m, v in series.items() if m >= start}
        for key, series in series_by_key.items()
    }


class _Unset:
    """ "Nobody said" — distinct from `None`, which says "unanchored"."""


_UNSET = _Unset()


def _opening_leg(anchor: BudgetAnchor | None, account_id: uuid.UUID) -> dict[date, Decimal] | None:
    """One card's `CardReserve.opening` leg — `{B−1: CCP Available}` on an
    anchored budget, None (an empty leg) everywhere else. The one spelling;
    the summary, `card_reserves` and the timeline all read it."""
    if anchor is None:
        return None
    return {
        anchor.openings.opening_month: anchor.openings.reserve_by_card.get(account_id, Decimal("0"))
    }


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
        anchor_repo: ImportAnchorRepository | None = None,
    ) -> None:
        self.account_repo = account_repo
        self.category_repo = category_repo
        self.category_group_repo = category_group_repo
        self.assignment_repo = assignment_repo
        self.transaction_repo = transaction_repo
        self.move_repo = move_repo
        self.snapshot_repo = snapshot_repo
        self.anchor_repo = anchor_repo
        self.changes = ChangeRecorder(assignment_repo.session)

    async def _budget_anchor(self, budget_id: uuid.UUID) -> BudgetAnchor | None:
        """The budget's import anchor, or None — None is today's code path."""
        if self.anchor_repo is None:
            return None
        return await self.anchor_repo.get_for_budget(budget_id)

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

    async def _load_envelope(self, budget_id: uuid.UUID, category_id: uuid.UUID):
        category = await self.category_repo.get(category_id)
        if category is None or str(category.budget_id) != str(budget_id):
            raise InvariantViolation("Category does not belong to this budget")
        return category

    async def _require_envelope(self, budget_id: uuid.UUID, category_id: uuid.UUID) -> None:
        """Money may LEAVE here. Income is the only refusal.

        A category in a system group is where income is *filed*, not an
        envelope: it never held money, so there is none to take out.

        Everything else may be a source, archived included — that is how a
        balance stranded in an archived envelope gets rescued, and Phase 3 of
        the archive flow depends on it.
        """
        category = await self._load_envelope(budget_id, category_id)
        group = await self.category_group_repo.get(category.category_group_id)
        if group is not None and group.is_system:
            raise InvariantViolation("Income categories do not hold money")

    async def _require_fundable(self, budget_id: uuid.UUID, category_id: uuid.UUID) -> None:
        """Money may ENTER here — `category_filters.IS_FUNDABLE`, served.

        A strictly narrower question than leaving, and it used to be the same
        check: `_require_envelope` tested the system group alone, under a
        comment claiming it was "the same rule" the pickers read. It was one of
        `IS_ASSIGNABLE`'s three terms, so money could be assigned into an
        archived envelope by anything that was not a picker — and land
        somewhere the budget page does not draw.

        A card's payment envelope is fundable and always was; that is how a
        card is paid down, and it is why this reads `IS_FUNDABLE` rather than
        `IS_ASSIGNABLE`, which now excludes it.
        """
        category = await self._load_envelope(budget_id, category_id)
        if category.is_fundable:
            return
        group = await self.category_group_repo.get(category.category_group_id)
        if group is not None and group.is_system:
            raise InvariantViolation("Income categories do not hold money")
        raise InvariantViolation(
            "That envelope is archived. Restore it before budgeting into it — "
            "money already in it can still be moved out"
        )

    async def get_category_balance(
        self,
        category_id: uuid.UUID,
        month: date,
        activity_by_month: dict[date, Decimal] | None = None,
        *,
        opening: tuple[date, Decimal] | None | _Unset = _UNSET,
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

        # The import anchor's single seam into the live path: guide, wishlist
        # and the category previews all read available through here, so one
        # opening kwarg reaches every one of them. A caller looping over a
        # budget's categories hands the seed in — it holds the budget id and
        # can load the anchor once — exactly as it already hands in activity;
        # `_UNSET` (not None) keeps "unanchored" distinguishable from "not
        # looked up yet".
        seed: tuple[date, Decimal] | None
        if isinstance(opening, _Unset):
            seed = (
                await self.anchor_repo.get_for_category(category_id)
                if self.anchor_repo is not None
                else None
            )
        else:
            seed = opening
        available = available_through(
            {a.month: a.assigned for a in assignments},
            activity_by_month,
            month_start,
            opening=seed,
        )

        return CategoryBalance(
            category_id=category_id,
            month=month_start,
            assigned=this_assigned,
            activity=this_activity,
            available=available,
        )

    async def card_walk(
        self,
        budget_id: uuid.UUID,
        month_start: date,
        *,
        categories: list[Category] | None = None,
    ) -> "CardWalk":
        """Everything the card model reads, assembled once.

        Extracted from `get_budget_summary` so other card surfaces — the
        import parity check reading every month of a reserve, the hygiene
        detectors attributing a negative one — never assemble these inputs a
        second time: a second assembly is exactly how the assignment leg once
        skipped the walk. `get_budget_summary` remains the only place a
        reserve becomes a served figure.

        `categories` is an optimization hand-off, not a variation point: the
        summary already holds the full list and passes it to avoid a second
        load; any other caller omits it.
        """
        anchor = await self._budget_anchor(budget_id)
        card_accounts = [
            a
            for a in await self.account_repo.get_all(budget_id, include_closed=True)
            if a.on_budget and a.classification == "liability"
        ]
        if not card_accounts:
            # The anchor still rides out: a cardless anchored budget serves
            # its anchor month (the client clamps navigation on it).
            return CardWalk(anchor=anchor)
        if categories is None:
            categories = await self.category_repo.get_all(budget_id, include_archived=True)
        month_end_date = last_of_month(month_start)
        linked_by_account = {
            cat.linked_account_id: cat for cat in categories if cat.linked_account_id
        }
        # `category_filters.SPENDABLE`, whose complement
        # `txn_filters.UNCLAIMED_CARD_ROW` selects on. Read from the
        # one expression rather than re-filtered out of `categories`: the
        # two spellings disagreed about income, so a rewards credit filed
        # to Ready to Assign on a card belonged to neither and the reserve
        # identity reported it as drift forever.
        spending_ids = await self.category_repo.spendable_ids(budget_id)
        spending_activity = await self.transaction_repo.sum_all_categories_by_month(
            spending_ids, end_date=month_end_date
        )
        assignments_by_cat: dict[uuid.UUID, dict[date, Decimal]] = {}
        for a in await self.assignment_repo.get_all_for_budget(budget_id):
            if a.month <= month_start:
                assignments_by_cat.setdefault(a.category_id, {})[a.month] = a.assigned
        credit_outflows = await self.transaction_repo.sum_credit_outflows_by_category(
            spending_ids, month_end_date
        )
        # `card_funding` runs the carryover simulation itself. The part of
        # a card inflow that repays uncovered debt has to be taken off the
        # month's activity *inside* that walk — subtracted after it, as a
        # cumulative total against a floored balance, it ratcheted upward
        # forever and rendered as overspending ("The Refused Repayment").
        # Card payment categories go in by card: their assignments are the
        # fifth leg of a reserve, and they have to retire the ride *inside*
        # the walk. Added afterwards — which is what the old
        # `set_aside_through(assignments, synthetic)` did — nothing ever
        # took them back out ("Two Ledgers, One Debt").
        card_categories = {
            account.id: linked.id
            for account in card_accounts
            if (linked := linked_by_account.get(account.id)) is not None
        }
        funding = card_funding(
            assignments_by_cat,
            spending_activity,
            credit_outflows,
            card_categories,
            openings=anchor.openings if anchor is not None else None,
        )
        payments = await self.transaction_repo.sum_card_payments_by_month(budget_id, month_end_date)
        unclaimed = await self.transaction_repo.sum_unclaimed_card_rows(budget_id, month_end_date)
        if anchor is not None:
            # The two reserve legs the domain walk never sees are repository
            # sums, so the anchor's truncation is applied here — the seed at
            # B−1 already accounts for everything earlier. Correctness lives
            # at this seam; bounding the queries themselves would be an
            # optimization, not a second rule.
            payments = _from_month(payments, anchor.month)
            unclaimed = _from_month(unclaimed, anchor.month)
        return CardWalk(
            card_accounts=card_accounts,
            linked_by_account=linked_by_account,
            funding=funding,
            payments=payments,
            unclaimed=unclaimed,
            credit_outflows=credit_outflows,
            anchor=anchor,
        )

    async def card_reserves(
        self, budget_id: uuid.UUID, month: date
    ) -> dict[uuid.UUID, tuple[str, CardReserve]]:
        """Each card's five-leg reserve through `month`, keyed by account —
        `{account_id: (name, CardReserve)}` — assembled by the same walk the
        summary serves.

        For callers that need a reserve's whole history rather than one
        month's figure: `CardReserve.set_aside` evaluates at any month, so
        the import parity check reads ten years of set-asides from one walk
        instead of one summary per month.
        """
        walk = await self.card_walk(budget_id, first_of_month(month))
        return {
            a.id: (
                a.name,
                card_reserve(
                    walk.funding,
                    a.id,
                    walk.payments.get(a.id, {}),
                    opening=_opening_leg(walk.anchor, a.id),
                ),
            )
            for a in walk.card_accounts
        }

    async def card_timeline_for(
        self, budget_id: uuid.UUID, account_id: uuid.UUID, month: date
    ) -> tuple[str, list["TimelineMonth"], "TimelineBreach | None", date | None] | None:
        """One card's reserve month by month, through `month`, with its first
        breach — `(name, timeline, breach, anchor_month)`, or None for an
        account that is not one of the budget's cards. `anchor_month` is B on
        an anchored budget (the timeline then opens at B−1, the seam row).

        The serving side of `domain/card_timeline.py`: the same walk the
        summary reads, evaluated at every month instead of the last one, with
        the balance series beside it so each month's `card_position` is
        against that month's balance rather than today's.
        """
        from igab.domain.card_timeline import card_timeline as build_timeline
        from igab.domain.card_timeline import first_breach

        month_start = first_of_month(month)
        walk = await self.card_walk(budget_id, month_start)
        account = next((a for a in walk.card_accounts if a.id == account_id), None)
        if account is None:
            return None
        balances = await self.account_repo.card_balances_by_month(
            budget_id, last_of_month(month_start)
        )
        reserve = card_reserve(
            walk.funding,
            account_id,
            walk.payments.get(account_id, {}),
            opening=_opening_leg(walk.anchor, account_id),
        )
        timeline = build_timeline(
            reserve,
            balances.get(account_id, {}),
            walk.funding.riding_by_card.get(account_id, {}),
            start=walk.anchor.openings.opening_month if walk.anchor is not None else None,
        )
        timeline = [cm for cm in timeline if cm.month <= month_start]
        anchor_month = walk.anchor.month if walk.anchor is not None else None
        return account.name, timeline, first_breach(timeline), anchor_month

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
        categories = await self.category_repo.get_all(budget_id, include_archived=True)
        groups = await self.category_group_repo.get_all(budget_id, include_archived=True)
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
            # One anchor load for the whole loop (memoized on the repo), and
            # none at all on an unanchored budget — the per-category lookup
            # would otherwise be a query per envelope on every summary.
            summary_anchor = await self._budget_anchor(budget_id)
            balance_map = {
                cat.id: await self.get_category_balance(
                    cat.id,
                    month_start,
                    activity_by_month=all_activity_by_month.get(cat.id, {}),
                    opening=category_opening(summary_anchor, cat.id),
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
        walk = await self.card_walk(budget_id, month_start, categories=categories)
        card_accounts, linked_by_account = walk.card_accounts, walk.linked_by_account
        funding, payments, unclaimed = walk.funding, walk.payments, walk.unclaimed
        if card_accounts:
            month_end_date = last_of_month(month_start)
            owed_by_card = await self.account_repo.card_balances(budget_id, month_end_date)
            # An anchored budget's identity needs each card's balance at the
            # anchor's B−1: a card imported holding a credit has no
            # post-anchor leg to explain it (`reserve_discrepancy`'s T3
            # opening_credit). Read live from the register, never stored, so
            # edits to pre-anchor rows stay coherent.
            #
            # `card_balances` returns a BALANCE — owed as a negative — so a
            # credit is the positive side and `max(0, ...)` below selects it.
            # Named for what it holds, not for `owed`: the sibling call above
            # is spelled `owed_by_card` and assigned straight to `balance`,
            # and a map whose name says owed but whose values say balance is
            # a sign error waiting for its second reader.
            balance_at_anchor: dict[uuid.UUID, Decimal] = {}
            if walk.anchor is not None:
                balance_at_anchor = await self.account_repo.card_balances(
                    budget_id, _month_end(walk.anchor.openings.opening_month)
                )
            # The card's own ledger for the viewed month, beside the reserve's
            # legs: what a person charged, and how far the debt actually moved.
            # Every leg above is a lifetime `sum_through`, so nothing here is
            # derivable client-side — and the debt moving DOWN is the one thing
            # a paydown does that the strip never said.
            month_flows = await self.account_repo.card_month_flows(
                budget_id, month_start, month_end_date
            )
            for account in card_accounts:
                linked = linked_by_account.get(account.id)
                # One assembler for all six legs. Composing a reserve at the
                # call site is what let the assignment leg skip the walk.
                reserve = card_reserve(
                    funding,
                    account.id,
                    payments.get(account.id, {}),
                    opening=_opening_leg(walk.anchor, account.id),
                )
                set_aside = reserve.set_aside(month_start)
                card_assignments = reserve.assignments
                opening_total = sum_through(reserve.opening, month_start)
                if linked is not None:
                    # The linked category's balance is this computation, not
                    # the transaction sums — nothing can be filed there, and
                    # its snapshot rows (assignments only) are ignored.
                    balance_map[linked.id] = CategoryBalance(
                        category_id=linked.id,
                        month=month_start,
                        assigned=card_assignments.get(month_start, zero),
                        activity=(
                            reserve.reservations.get(month_start, zero)
                            - reserve.released.get(month_start, zero)
                            - reserve.residual.get(month_start, zero)
                            - reserve.payments.get(month_start, zero)
                        ),
                        available=set_aside,
                        is_card_payment=True,
                    )
                balance = owed_by_card.get(account.id, zero)
                # One implementation of "where does this card stand", shared
                # with `reserve_discrepancy`. It used to be spelled again here.
                position = card_position(set_aside, balance)
                charged, received, pending = month_flows.get(account.id, (zero, zero, zero))
                if account.is_closed and balance == zero and set_aside == zero:
                    # Settled and closed: nothing owed, nothing reserved,
                    # nothing to act on. The arithmetic above still ran — the
                    # linked category's balance_map entry keeps the envelope
                    # term honest — only the row is skipped. A closed card
                    # with anything left keeps its row (tagged via
                    # `is_closed`) until someone moves the money out.
                    continue
                cards.append(
                    CardStatus(
                        account_id=account.id,
                        name=account.name,
                        category_id=linked.id if linked else None,
                        balance=balance,
                        set_aside=set_aside,
                        # Owed beyond the reserve. A negative set-aside
                        # reserves nothing, so it is floored before
                        # subtracting — see `card_position`.
                        uncovered=position.uncovered,
                        # The other three terms of the same position. Served
                        # because a zero `reserve_discrepancy` means the
                        # identity's bounds hold, NOT that the number on
                        # screen is sensible: an over-reserve explained by
                        # assignments and a negative reserve explained by
                        # residual both report nothing there. The surface
                        # reads these to say WHICH way a card is unusual.
                        over_reserved=position.over_reserved,
                        short_reserved=position.short_reserved,
                        card_credit=position.card_credit,
                        is_closed=account.is_closed,
                        overspent_this_month=funding.floored_by_card.get(account.id, {}).get(
                            month_start, zero
                        ),
                        assigned=sum_through(card_assignments, month_start),
                        reserved=sum_through(reserve.reservations, month_start),
                        released=sum_through(reserve.released, month_start),
                        residual=sum_through(reserve.residual, month_start),
                        payments=sum_through(reserve.payments, month_start),
                        opening=opening_total,
                        riding=sum_through(funding.riding_by_card.get(account.id, {}), month_start),
                        charged_this_month=-charged,
                        inflows_this_month=received,
                        paid_this_month=reserve.payments.get(month_start, zero),
                        debt_change_this_month=charged + received,
                        pending_this_month=pending,
                        # Sorted so the panel can name the earliest month that
                        # still has debt riding on it — that is the one whose
                        # envelope is worth back-funding first.
                        rode_by_month=sorted(
                            (m, v)
                            for m, v in funding.floored_by_card.get(account.id, {}).items()
                            if m <= month_start and v != zero
                        ),
                        # Every defect this model has had was visible here, and
                        # the invariant that would have caught them excused
                        # exactly the histories that produce them. Computed
                        # where all six inputs are already in hand, and read
                        # back by the integrity check rather than re-derived.
                        # On an anchored budget the opening reserve is folded
                        # into `assigned` — YNAB's accumulated CCP position is
                        # a pre-anchor net assignment, and it enters T1 and T2
                        # with exactly an assignment's signs. `opening_credit`
                        # is the T3 allowance for a card imported in credit.
                        reserve_discrepancy=reserve_discrepancy(
                            set_aside,
                            balance,
                            opening_total + sum_through(card_assignments, month_start),
                            sum_through(funding.covered_by_card.get(account.id, {}), month_start),
                            sum_through(reserve.payments, month_start),
                            sum_through(reserve.residual, month_start),
                            sum_through(unclaimed.get(account.id, {}), month_start),
                            opening_credit=max(zero, balance_at_anchor.get(account.id, zero)),
                        ),
                    )
                )
            uncovered_current = sum(
                (
                    by_month.get(month_start, zero)
                    for by_month in funding.floored_by_category.values()
                ),
                zero,
            )

        balances: list[CategoryBalance] = []
        total_category_balance = Decimal("0")
        total_assigned = Decimal("0")
        total_activity = Decimal("0")
        total_overspent = Decimal("0")
        total_overspent_credit = Decimal("0")
        overspent_count = 0
        overspent_count_cash = 0

        for cat in categories:
            bal = balance_map[cat.id]
            # Decided once, here, and carried on the row: every consumer —
            # the month endpoint, Cover Overspent, the Guide's checkup — reads
            # the flag rather than re-deriving which groups are system.
            bal.in_system_group = cat.category_group_id in system_group_ids
            bal.is_card_payment = cat.linked_account_id is not None
            # A card inflow filed here raised this envelope through the
            # ordinary activity sum. The part of it that repaid *uncovered*
            # debt has to come back off: the card's balance fell but no cash
            # arrived, so the envelope cannot spend it (domain/cards.py
            # `release_split`). The part that released reserved cash stays —
            # that money was already the envelope's.
            #
            # The adjustment lives INSIDE the carryover walk, which is why
            # `available` is re-read out of `card_funding`'s series rather
            # than decremented here. Applied afterwards, as a running total
            # against a floored balance, it survived into every later month
            # and grew without bound. Only categories the walk actually
            # corrected are re-read: for the rest the series is identical, and
            # recomputing it would give the snapshot path a second opinion.
            repaid = funding.repaid_by_category.get(cat.id)
            if repaid and not bal.in_system_group and not bal.is_card_payment:
                bal.repaid_uncovered_debt = repaid.get(month_start, zero)
                bal.activity -= bal.repaid_uncovered_debt
                bal.available = available_at(funding.end_balances[cat.id], month_start)
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
                # Straight out of the dict `uncovered_current` is summed from,
                # so the row and the Ready to Assign arithmetic cannot tell
                # different stories. It cannot exceed the shortfall: both are
                # read off the same adjusted month-end series, and
                # `credit_floored` caps the ride at that month's deficit.
                #
                # No red here is an artefact of the card correction. A
                # repayment is bounded by the inflow that caused it, so at
                # worst it returns the month to what it would have been with
                # no refund at all — it cannot push a month negative that was
                # not already negative. That is what lets Cover Overspent
                # trust this split; the previous rule's counterweight could
                # manufacture a shortfall no assignment was able to fix.
                bal.credit_overspent = funding.floored_by_category.get(cat.id, {}).get(
                    month_start, zero
                )
                total_overspent += -bal.available
                total_overspent_credit += bal.credit_overspent
                overspent_count += 1
                if -bal.available > bal.credit_overspent:
                    overspent_count_cash += 1
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
            total_overspent_cash=total_overspent - total_overspent_credit,
            total_overspent_credit=total_overspent_credit,
            overspent_count=overspent_count,
            overspent_count_cash=overspent_count_cash,
            assigned_in_future=assigned_in_future,
            category_balances=balances,
            cards=cards,
            anchor_month=walk.anchor.month if walk.anchor is not None else None,
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

        # The same anchor the live path applies (`get_category_balance`), so
        # the cache and the fallback cannot disagree. Anchored: each category
        # opens at YNAB's B−1 Available (zero when unlisted) and pre-anchor
        # months are never emitted; the B−1 row then serves every later
        # month's floored carryover through the existing snapshot read.
        anchor = await self._budget_anchor(budget_id)

        rows: list[dict[str, object]] = []
        for cat in categories:
            asg = assigned_by_cat.get(cat.id, {})
            act = activity.get(cat.id, {})
            # One loop, the domain's: these rows must be exactly what
            # `available_through` would say, month by month.
            for m, end_of_month in monthly_end_balances(
                asg, act, opening=category_opening(anchor, cat.id)
            ).items():
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

        categories = await self.category_repo.get_all(budget_id, include_archived=True)
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
        # Only an INCREASE has to clear the funding rule. Setting an archived
        # envelope's assignment down — to zero, or anywhere below where it
        # stands — is money coming back out, which is always allowed and is
        # what the archive sweep does.
        if amount > before_assigned:
            await self._require_fundable(budget_id, category_id)
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

        # Asymmetric on purpose: leaving is always allowed, entering is not.
        # Both used to run the same check, which is how money could be moved
        # into an envelope the budget page no longer draws.
        if from_category_id is not None:
            await self._require_envelope(budget_id, from_category_id)
        if to_category_id is not None:
            await self._require_fundable(budget_id, to_category_id)

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
        """Current summary plus {category_id: cash shortfall} for envelope
        categories. Hidden categories are included on purpose — they participate
        in the TBA math, so covering them is required to zero out overspending.

        The **cash** part only. Credit-funded overspending is money that rode
        onto a card: it is already counted in that card's Uncovered, it does not
        charge Ready to Assign now, and at the month boundary it rolls onto the
        card rather than being written off. Assigning cash to it buys nothing —
        the debt stays, and the dollars leave Ready to Assign for an envelope
        that will floor to zero regardless. A category overspent entirely on a
        card therefore produces no row here at all.

        The glossary has said this since the credit model shipped ("Cover
        Overspent handles only the cash kind, on purpose"); until now only the
        glossary said it."""
        summary = await self.get_budget_summary(budget_id, month)
        shortfalls = {
            b.category_id: -b.available - b.credit_overspent
            for b in summary.category_balances
            if b.available < 0 and not b.in_system_group and not b.is_card_payment
        }
        return summary, {k: v for k, v in shortfalls.items() if v > 0}

    async def cover_overspent_preview(
        self, budget_id: uuid.UUID, month: date
    ) -> CoverOverspentPreview:
        summary, shortfalls = await self._overspent_shortfalls(budget_id, month)
        proposed = distribute_cover(shortfalls, summary.to_be_assigned)

        categories = await self.category_repo.get_all(budget_id, include_archived=True)
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
            total_overspent=sum(shortfalls.values(), Decimal("0")),
            total_overspent_credit=summary.total_overspent_credit,
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
