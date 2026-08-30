import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel

from igab.api.v1.schemas.tag import TagOutSimple
from igab.domain.enums import TargetStatus, TargetType
from igab.domain.money import Money


class CategoryGroupCreate(BaseModel):
    name: str
    #: Omit it and the group goes last — the server assigns positions, so a
    #: client can no longer send a count of the rows it happened to be showing.
    sort_order: int | None = None


class CategoryGroupReorder(BaseModel):
    #: The budget's visible groups, in the order they should appear. Each
    #: exactly once; hidden and system groups may be omitted and keep their
    #: slot — see CategoryGroupRepository.reorder.
    group_ids: list[uuid.UUID]


class CategoryReorder(BaseModel):
    #: One group's visible categories, in the order they should appear. Each
    #: exactly once; hidden ones may be omitted — see CategoryRepository.reorder.
    category_ids: list[uuid.UUID]


class CategoryDeletePreviewResponse(BaseModel):
    """What deleting these categories is about to do.

    The dialog states these numbers before the user commits, and a differential
    test pins them against what the delete then actually does — a confirmation
    that misreports money is worse than no confirmation.
    """

    category_ids: list[uuid.UUID]
    category_names: list[str]
    transaction_count: int
    #: Of those, how many are reconciled. Called out because those rows cannot
    #: be re-filed by hand afterwards without unreconciling them first.
    reconciled_count: int
    available: Decimal
    future_assigned: Decimal
    payee_count: int
    scheduled_count: int
    #: Net posted spending filed here over the categories' whole life
    #: (positive = outflow). Moving hands it to the destination along with the
    #: assignment that covered it, so the destination's balance is unchanged;
    #: uncategorizing sends it out of category-keyed reports until re-filed.
    #: Required, not optional — the dialog states it either way.
    moving_activity: Decimal
    #: What Ready to Assign gains in the viewed month, one figure per mode —
    #: they differ when activity dated after the viewed month moves (its
    #: cover is a future assignment the viewed month's TBA already counts).
    #: The dialog shows the one for the selected mode; it never derives money.
    released_if_moved: Decimal
    released_if_uncategorized: Decimal
    #: Reasons the delete would be refused outright (a linked payment or debt
    #: category). Non-empty means the confirm button stays disabled.
    blocked_by: list[str]
    #: Nothing to decide — the client may delete without showing the dialog.
    is_empty: bool


class CategoryDeleteResultResponse(BaseModel):
    #: The single change-log row this delete produced; undo it to reverse the
    #: whole operation.
    change_id: uuid.UUID
    category_ids: list[uuid.UUID]
    transactions_moved: int
    transactions_uncategorized: int
    assignments_removed: int
    released: Decimal


class CategoryDeleteRequest(BaseModel):
    """Delete one or many categories as a single operation.

    A list rather than a call per category: the budget page deletes
    multi-selections, and N separate deletes would write N change rows for
    what the user experienced as one action — N cards in Activity, N undo
    clicks to reverse it, and N chances for one of them to fail halfway.
    """

    category_ids: list[uuid.UUID]
    #: Re-file their transactions here. Null leaves the rows genuinely
    #: uncategorized, carrying provenance so the register can say what they
    #: used to be.
    move_to: uuid.UUID | None = None
    #: The month whose Ready to Assign the reported figures refer to.
    month: datetime.date | None = None


class CategoryDeletePreviewRequest(BaseModel):
    category_ids: list[uuid.UUID]
    month: datetime.date | None = None


class RepairOrphansResponse(BaseModel):
    """What the hygiene repair found and fixed."""

    categories_repaired: int
    transactions_uncategorized: int
    assignments_removed: int
    #: Money returning to Ready to Assign — a visible change to the user's
    #: numbers, so the toast states it rather than letting them find it.
    released: Decimal
    #: One per repaired category, each independently undoable.
    change_ids: list[uuid.UUID]
    #: Live categories sitting under a deleted group: invisible on the budget
    #: page but still in the summary arithmetic. Reported rather than repaired
    #: — the fix is to restore the group or delete them deliberately, and this
    #: action has no basis for choosing.
    categories_under_deleted_groups: int


class CategoryGroupUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None
    is_archived: bool | None = None


class CategoryGroupResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    sort_order: int
    is_archived: bool
    is_system: bool
    #: Every live category in this group is a card's set-aside envelope, so the
    #: budget grid draws no header for it (`GROUP_IS_CARD_ONLY`).
    #:
    #: Served rather than derived because the client cannot compute it — its
    #: category list filters hidden categories, so a group whose only non-card
    #: row is hidden reads as card-only there and not here. It had been deriving
    #: it anyway, and `CategoryGroupRepository.reorder` had a second, narrower
    #: idea of which groups the grid skips, so dragging a group was refused
    #: outright on any budget with a card group.
    #:
    #: Required, not optional: a path that forgets it must raise, not silently
    #: draw an empty "Credit Card Payments" header and turn reordering off.
    is_card_only: bool
    #: 'wishlist' for the group the Guide keeps; rename and delete are refused.
    system_key: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    category_group_id: uuid.UUID
    name: str
    subtitle: str | None = None
    #: Omit it and the category goes last in its group — see CategoryGroupCreate.
    sort_order: int | None = None
    note: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    subtitle: str | None = None
    sort_order: int | None = None
    note: str | None = None
    is_archived: bool | None = None
    category_group_id: uuid.UUID | None = None


class CategoryTargetCreate(BaseModel):
    target_type: TargetType
    target_amount: Money
    target_date: datetime.date | None = None
    repeat_frequency: str | None = None


class CategoryTargetResponse(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    target_type: str
    target_amount: Decimal
    target_date: datetime.date | None
    repeat_frequency: str | None

    model_config = {"from_attributes": True}


class CategoryBalance(BaseModel):
    category_id: uuid.UUID
    month: datetime.date
    #: Null on a category in a system (Income) group: income is filed there,
    #: not budgeted there, so it has no envelope money. Its `activity` is the
    #: income received that month; what is free to assign is `to_be_assigned`.
    #: Served as null rather than the lifetime total the carryover arithmetic
    #: would otherwise produce — 1.6M on one imported budget, directly under a
    #: hero named Ready to Assign.
    assigned: Decimal | None
    activity: Decimal
    available: Decimal | None
    #: The target verdict, computed by TargetService — the same function Fill
    #: Underfunded asks. The budget row's pill renders this; it does not
    #: recompute it. A second implementation in the client drifted from this
    #: one in three separate ways before it was removed.
    #:
    #: None when the category has no target, which is a genuine third state
    #: rather than a missing value — unlike `needs_category`, whose absence
    #: could only ever mean a path forgot to load it.
    target_status: TargetStatus | None = None
    #: What still has to be assigned this month for the target to be met, and
    #: exactly what Fill Underfunded would move. None when there is no target.
    needed_this_month: Decimal | None = None
    #: A card's set-aside envelope (linked to the card account). Not drawn in
    #: the category grid — the cards section owns it — and never counted as
    #: overspending; its state reads as the card's Set aside / Uncovered.
    #: Required, not optional: a path that forgets it must raise, not draw
    #: every card envelope as an ordinary row.
    is_card_payment: bool
    #: How much of THIS MONTH's card inflows filed here repaid uncovered debt
    #: instead of returning money to this envelope (domain/cards.py
    #: `release_split`). The card owes less; no cash arrived, so this envelope
    #: cannot spend it. Almost always 0.
    #:
    #: Already inside `available` — it is an adjustment to the month's activity
    #: made within the carryover walk, not a deduction applied after it — which
    #: is also why `activity` here differs from the register's raw sum by
    #: exactly this amount.
    #:
    #: Served rather than derived because the client cannot compute it: it
    #: needs every month's exposure walk per (category, card). It exists so the
    #: adjustment is never silent; money moving with nothing on screen to
    #: explain it was the whole defect this model keeps producing.
    #:
    #: **This month's, never a running total.** Its predecessor was cumulative
    #: since inception, subtracted from a floored carryover, and reached ~31x
    #: its first year's value on a real budget — all of it drawn as red.
    repaid_uncovered_debt: Decimal
    #: How much of this row's red was spent on a card (domain/cards.py). Zero
    #: whenever `available` is not negative.
    #:
    #: It answers "does this cost me anything": it does not. Credit-funded red
    #: never charges Ready to Assign — at the month boundary it rides onto the
    #: card as Uncovered instead of being written off — so a row where this
    #: equals the whole shortfall wants a calmer treatment than one funded by
    #: cash, and Cover Overspent does not offer to fund it.
    #:
    #: Required, not optional. A default of 0 would quietly re-draw every
    #: credit overspend as cash, which is the failure this field exists to end.
    credit_overspent: Decimal


class CategoryResponse(BaseModel):
    id: uuid.UUID
    category_group_id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    subtitle: str | None
    sort_order: int
    note: str | None
    is_archived: bool
    linked_account_id: uuid.UUID | None
    #: The liability that owns this category, if any. Exposed because the
    #: liability-binding screen's rule needs it: without it the client could
    #: not tell a free category from one another liability already owns, and
    #: offered both.
    linked_liability_id: uuid.UUID | None
    #: May money be budgeted or moved into this envelope? Computed by the
    #: server from `IS_ASSIGNABLE` (repositories/category_filters.py).
    #:
    #: Required, not optional, for the same reason `needs_category` is: a path
    #: that forgets to load it should raise rather than report every category
    #: as ineligible, which would empty the move-money picker silently.
    is_assignable: bool
    #: May money ENTER this envelope? `IS_FUNDABLE`, not the same question as
    #: what a picker may offer: a card's payment envelope is fundable (that is
    #: how a card is paid down) and offered by nothing. The two were one field
    #: read two ways, and each side got the other's answer — a paydown target
    #: never filled, and money could be assigned into an archived envelope.
    #:
    #: Required for the same reason its siblings are.
    is_fundable: bool
    #: May a transaction leg be filed here? Differs from is_assignable on
    #: system groups — income is filed into one — and on linked categories.
    is_categorizable: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
    tags: list[TagOutSimple] = []

    model_config = {"from_attributes": True}


class CardStatusOut(BaseModel):
    """One card in the budget's cards section.

    `balance` is the ledger through the viewed month (negative = owed);
    `set_aside` is cash reserved for it (its envelope's available, may be
    negative when payments outran the reserve); `uncovered` is owed beyond
    the reserve — calm and informational: a due date crossing the month
    boundary is a normal state, not overspending."""

    account_id: uuid.UUID
    name: str
    #: Null only before the envelope exists (fresh migration edge) — the row
    #: still renders, assignment has nowhere to land until it appears.
    category_id: uuid.UUID | None
    balance: Decimal
    set_aside: Decimal
    uncovered: Decimal
    #: A settled closed card sends no row at all; a closed card with a
    #: residual balance or reserve keeps one, and this is how the section
    #: knows to tag it. Required, not optional — a path that forgets must
    #: raise, not render a closed card as open.
    is_closed: bool
    #: The part of this month's overspending riding on this card. Included in
    #: `uncovered` already; served so a budget with more than one card can say
    #: which card carries it, since they are paid separately.
    overspent_this_month: Decimal
    #: 0 when this card's reserve identity holds with all three of its bounds
    #: met, otherwise the amount by which one does not (domain/cards.py
    #: `reserve_discrepancy`). The integrity check reads this rather than
    #: re-deriving it, so the page and the check cannot disagree about whether
    #: a card's reserve makes sense.
    #:
    #: Required, not optional: a path that forgets it must raise, not report a
    #: drifting reserve as healthy.
    reserve_discrepancy: Decimal


class BudgetMonthResponse(BaseModel):
    month: datetime.date
    to_be_assigned: Decimal
    #: Envelope categories only — income appears in `to_be_assigned` and in
    #: its own rows' `activity`, never here.
    total_assigned: Decimal
    total_activity: Decimal
    total_overspent: Decimal
    #: How many categories make up total_overspent — counted server-side in the
    #: same loop, so the count and the amount are always about the same set.
    #:
    #: Required, no default. A default of 0 would let a path that forgets it
    #: report "nothing overspent" rather than raising, which is the wrong
    #: failure direction for a number the user reads as a workload.
    overspent_count: int
    #: `total_overspent` split by what funded it. The headline stays whole —
    #: the red on the grid is real either way — but only the cash part can ever
    #: charge Ready to Assign, so that is the figure any call to action reads.
    #: The credit part rolls onto its card at the month boundary and needs no
    #: action at all.
    #:
    #: Required for the same reason `overspent_count` is: a default would let a
    #: path that forgets report the calm number as the whole story.
    total_overspent_cash: Decimal
    total_overspent_credit: Decimal
    #: How many categories carry a cash shortfall — the count Cover Overspent
    #: will list, which is at most `overspent_count`.
    overspent_count_cash: int
    # Committed to months after this one; already deducted from to_be_assigned
    assigned_in_future: Decimal = Decimal("0")
    category_balances: list[CategoryBalance]
    #: The budget's cards — balance / set aside / uncovered (domain/cards.py).
    #: Empty when the budget has none; the budget page draws its cards
    #: section from exactly this, computing nothing.
    cards: list[CardStatusOut] = []


class AssignmentUpdate(BaseModel):
    amount: Money


class FutureOverspendItem(BaseModel):
    """One (category, month, delta) probe: the signed amount change a pending
    transaction edit would apply — outflow negative, reversals positive."""

    category_id: uuid.UUID
    date: datetime.date
    amount_delta: Money


class FutureOverspendPreviewRequest(BaseModel):
    items: list[FutureOverspendItem]


class FutureOverspendWarningOut(BaseModel):
    category_id: uuid.UUID
    category_name: str
    month: datetime.date
    available_before: Decimal
    available_after: Decimal


class FutureOverspendPreviewResponse(BaseModel):
    warnings: list[FutureOverspendWarningOut]


class MoveMoneyRequest(BaseModel):
    """Move money between envelopes; a null side means To-Be-Assigned."""

    from_category_id: uuid.UUID | None = None
    to_category_id: uuid.UUID | None = None
    amount: Money
    month: datetime.date


class BudgetMoveResponse(BaseModel):
    id: uuid.UUID
    month: datetime.date
    from_category_id: uuid.UUID | None
    to_category_id: uuid.UUID | None
    amount: Decimal
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class CategoryHistoryResponse(BaseModel):
    category_id: uuid.UUID
    last_month_assigned: Decimal
    last_month_spent: Decimal
    average_assigned: Decimal
    average_spent: Decimal
    months_included: int


class CategoryHistoryBatchRequest(BaseModel):
    category_ids: list[uuid.UUID]


class AutoAssignRequest(BaseModel):
    category_ids: list[uuid.UUID]
    action: str
    month: datetime.date


class CoverOverspentPreviewItem(BaseModel):
    category_id: uuid.UUID
    category_name: str
    overspent: Decimal
    proposed_addition: Decimal
    remaining_after: Decimal


class CoverOverspentPreviewResponse(BaseModel):
    items: list[CoverOverspentPreviewItem]
    #: What `items` sums to: the cash shortfall, the whole of what this dialog
    #: can act on.
    total_overspent: Decimal
    #: Overspending deliberately left out of `items` because it rode onto a
    #: card. Served so the dialog can state the difference between itself and
    #: the grid's red, rather than leaving a gap for the reader to find.
    total_overspent_credit: Decimal
    total_addition: Decimal
    tba_before: Decimal
    tba_after: Decimal


class CoverOverspentApplyItem(BaseModel):
    category_id: uuid.UUID
    proposed_addition: Money


class CoverOverspentApplyRequest(BaseModel):
    month: datetime.date
    items: list[CoverOverspentApplyItem]


class AssignStrategyTotal(BaseModel):
    strategy: str
    total_amount: Decimal
    total_needed: Decimal | None = None
    to_assign: Decimal
    to_return: Decimal
    affected_count: int


class AssignStrategyTotalsResponse(BaseModel):
    month: datetime.date
    tba: Decimal
    total_overspent: Decimal
    #: The part of `total_overspent` that Cover Overspending would actually
    #: fund — the rest rode onto a card and needs no assignment. The dropdown
    #: row reads this, so the number on it matches the dialog it opens.
    total_overspent_cash: Decimal
    strategies: list[AssignStrategyTotal]


class AssignPreviewItemOut(BaseModel):
    category_id: uuid.UUID
    category_name: str
    current_assigned: Decimal
    delta: Decimal
    new_assigned: Decimal


class AssignPreviewResponse(BaseModel):
    strategy: str
    items: list[AssignPreviewItemOut]
    total_needed: Decimal | None = None
    to_assign: Decimal
    to_return: Decimal
    tba_before: Decimal
    tba_after: Decimal


class AssignApplyRequest(BaseModel):
    month: datetime.date
    strategy: str


class AssignApplyResponse(BaseModel):
    to_assign: Decimal
    to_return: Decimal
    categories_changed: int
    tba_after: Decimal
    # Change-log batch for undo; null when the strategy moved nothing
    batch_id: uuid.UUID | None = None


class CoverOverspentApplyResponse(BaseModel):
    batch_id: uuid.UUID | None = None


class RecentPayeeResponse(BaseModel):
    """Most recent payee used in a category — powers add-transaction prefill."""

    payee_id: uuid.UUID
    name: str


# ─── Category classification ─────────────────────────────────────────────────


class CategoryClassSlice(BaseModel):
    activity_class: str
    label: str
    total: Decimal
    count: int


class CategoryClassification(BaseModel):
    """How this category's recent activity counts in reports.

    The badge contract: `dominant` is set only when a single non-spending
    class covers more than half of the category's outflow in the window —
    that is when a category deserves a tag like "Debt payment" next to its
    name, and when its absence from a spending report needs explaining
    before the user ever opens one.
    """

    #: Outflow by class over the window, largest first. Empty = no activity.
    classes: list[CategoryClassSlice]
    window_months: int = 12
    dominant: str | None = None
    dominant_label: str | None = None
    explanation: str | None = None
