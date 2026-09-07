import datetime
import uuid
from decimal import Decimal
from typing import Any

from pydantic import Field

from igab.api.v1.schemas.base import ApiModel
from igab.api.v1.schemas.tag import TagOutSimple
from igab.domain.enums import TargetStatus, TargetType
from igab.domain.money import Money
from igab.domain.targets import MAX_FUNDING_DAY


class CategoryGroupCreate(ApiModel):
    name: str
    #: Omit it and the group goes last — the server assigns positions, so a
    #: client can no longer send a count of the rows it happened to be showing.
    sort_order: int | None = None


class CategoryGroupReorder(ApiModel):
    #: The budget's visible groups, in the order they should appear. Each
    #: exactly once; hidden and system groups may be omitted and keep their
    #: slot — see CategoryGroupRepository.reorder.
    group_ids: list[uuid.UUID]


class CategoryReorder(ApiModel):
    #: One group's visible categories, in the order they should appear. Each
    #: exactly once; hidden ones may be omitted — see CategoryRepository.reorder.
    category_ids: list[uuid.UUID]


class CategoryReferenceResponse(ApiModel):
    """One kind of thing still pointing at the categories being deleted.

    `clearable` is the whole point of the split. A saved view placing this
    category means nothing once it is gone, so removing it costs nothing and
    the dialog can say so plainly. A recorded money move is a fact about what
    happened, and severing it would leave a row saying money went nowhere.
    """

    kind: str
    label: str
    count: int
    clearable: bool


class CategoryDeletePreviewResponse(ApiModel):
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
    #: Everything else still pointing at these categories, named so the dialog
    #: can list the contact points rather than leaving the user to guess why a
    #: delete behaves the way it does.
    references: list[CategoryReferenceResponse]
    #: May the row be removed outright rather than soft-deleted? False whenever
    #: anything *records* that the category existed. Served rather than derived
    #: from `references`, so the dialog's wording and the delete's behaviour
    #: cannot disagree about which one is about to happen.
    may_hard_delete: bool
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
    #: Group deletes only: how many of the group's categories are archived,
    #: and whether that is every one of them. The dialog then leads with
    #: "Archive group instead" — a group of archived envelopes is usually one
    #: the person wants off the grid, not one whose history should go.
    archived_count: int = 0
    all_archived: bool = False


class CategoryDeleteResultResponse(ApiModel):
    #: The single change-log row this delete produced; undo it to reverse the
    #: whole operation.
    change_id: uuid.UUID
    category_ids: list[uuid.UUID]
    transactions_moved: int
    transactions_uncategorized: int
    assignments_removed: int
    released: Decimal


class CategoryDeleteRequest(ApiModel):
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


class CategoryDeletePreviewRequest(ApiModel):
    category_ids: list[uuid.UUID]
    month: datetime.date | None = None


class ArchivedCategoryResponse(ApiModel):
    """One row of the archived listing — the modal's only source of truth.

    `available` should be zero for anything archived through the flow, which
    refuses otherwise. It is served anyway because rows archived before that
    existed can carry a balance, and the budget page no longer draws them: this
    listing is the only place that money is visible at all.
    """

    id: uuid.UUID
    name: str
    group_id: uuid.UUID
    group_name: str
    transaction_count: int
    archived_at: datetime.datetime | None
    available: Decimal
    #: True when the row is archived because its *group* is. Restoring the
    #: category alone does nothing in that case, so the modal offers the group
    #: instead — required, not optional, so a path that forgets it raises
    #: rather than drawing a button that silently no-ops.
    group_is_archived: bool


class CategoryArchiveRequest(ApiModel):
    """Archive or restore a selection, as one operation and one undo row."""

    category_ids: list[uuid.UUID]
    month: datetime.date | None = None


class CategoryGroupArchiveRequest(ApiModel):
    """Archive or restore a whole group. The group is in the path; the month
    only decides which month's balances the refusal is measured against."""

    month: datetime.date | None = None


class CategoryArchivePreviewResponse(ApiModel):
    """What archiving would do, and what stands in the way.

    `may_archive` is served rather than derived from the three lists: the dialog
    disables its button on one field, and a client recomputing the condition is
    how the button and the endpoint come to disagree about whether an archive
    is allowed.
    """

    category_ids: list[uuid.UUID]
    category_names: list[str]
    transaction_count: int
    available: Decimal
    future_assigned: Decimal
    blocked_by_balance: list[str]
    blocked_by_link: list[str]
    blocked_by_schedule: list[str]
    may_archive: bool


class RepairOrphansResponse(ApiModel):
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


class CategoryGroupUpdate(ApiModel):
    """No `is_archived`. Archiving is not a field edit: it takes every envelope
    under the group off the budget, so it goes through
    `POST /category-groups/{id}/archive`, which refuses while any of them still
    holds money. Accepting the flag here was a second way to set the same state
    that skipped the rule — the exact door this release closed on the client."""

    name: str | None = None
    sort_order: int | None = None


class CategoryGroupResponse(ApiModel):
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
    #: How many of this group's live categories are archived — envelopes the
    #: budget grid does not draw. Zero for almost every group; when it is not,
    #: the grid can stop calling the group empty, and the delete dialog can say
    #: why it is naming categories that are nowhere on the page.
    #:
    #: Served rather than counted on the client for `is_card_only`'s reason:
    #: the client's category list filters archived rows, so it is missing the
    #: input. Required, not optional — a path that forgets must raise.
    archived_category_count: int
    #: 'wishlist' for the group the Guide keeps; rename and delete are refused.
    system_key: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class CategoryCreate(ApiModel):
    category_group_id: uuid.UUID
    name: str
    subtitle: str | None = None
    #: Omit it and the category goes last in its group — see CategoryGroupCreate.
    sort_order: int | None = None
    note: str | None = None


class CategoryUpdate(ApiModel):
    """No `is_archived` — see `CategoryGroupUpdate`. Use
    `POST /categories/archive` and `/unarchive`, which run the refusal."""

    name: str | None = None
    subtitle: str | None = None
    sort_order: int | None = None
    note: str | None = None
    category_group_id: uuid.UUID | None = None


class CategoryTargetCreate(ApiModel):
    target_type: TargetType
    target_amount: Money
    #: Savings balance only: paces the shortfall over the months left.
    target_date: datetime.date | None = None
    #: Before this day of the current month an unmet target reads "pending";
    #: None defers to the budget's funding_day.
    check_after_day: int | None = Field(default=None, ge=1, le=MAX_FUNDING_DAY)
    #: Weekly funding only, and required for it: 0=Monday … 6=Sunday.
    weekday: int | None = Field(default=None, ge=0, le=6)


class CategoryTargetResponse(ApiModel):
    id: uuid.UUID
    category_id: uuid.UUID
    target_type: str
    target_amount: Decimal
    target_date: datetime.date | None
    check_after_day: int | None
    weekday: int | None

    model_config = {"from_attributes": True}


class CategoryBalance(ApiModel):
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
    #: It answers "what happens if I leave it": credit-funded red never charges
    #: Ready to Assign — at the month boundary it rides onto the card as
    #: Uncovered instead of being written off — so a row where this equals the
    #: whole shortfall wants a calmer treatment than one funded by cash.
    #:
    #: It is NOT a reason to withhold funding: covering it retires the card's
    #: debt (see `BudgetService._overspent_shortfalls`, which measured it), so
    #: Cover Overspending offers the whole red and names this part.
    #:
    #: Required, not optional. A default of 0 would quietly re-draw every
    #: credit overspend as cash, which is the failure this field exists to end.
    credit_overspent: Decimal


class CategoryResponse(ApiModel):
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


class RodeMonth(ApiModel):
    """One month that put riding debt on a card, and how much.

    A month, not just a total, because the two remedies differ by it: an
    assignment to the card covers a ride from any month, while funding the
    envelope only retires the ride if it lands in the month that ended short.
    The walk is recomputed from scratch on every request, so a backdated
    assignment does retire it — which is the cheaper fix, and the one nothing
    in the app used to name.
    """

    month: datetime.date
    amount: Decimal


class RodeCategory(ApiModel):
    """One envelope that rode onto this card in the viewed month.

    The breakdown of `overspent_this_month`, which it sums to exactly. It
    exists so a red envelope Cover Overspent will not touch can be traced to
    the card carrying it — the one question the budget page could not answer
    about its own figure.
    """

    category_id: uuid.UUID
    category_name: str
    amount: Decimal


class CardStatusOut(ApiModel):
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
    #: The legs `set_aside` is the running total of, each through the
    #: viewed month, plus what is still riding uncovered on the card:
    #:
    #:     opening + assigned + reserved − released − residual − payments
    #:         == set_aside
    #:
    #: The surface used to show only the total, and every question this model
    #: raised was answered by decomposing it. The client renders these; it
    #: must not sum them into a set-aside of its own.
    #:
    #: Required, not optional, all seven — a path that forgets must raise
    #: rather than show a reserve made of zeros.
    assigned: Decimal
    reserved: Decimal
    released: Decimal
    residual: Decimal
    payments: Decimal
    #: The sixth leg, first in time: YNAB's own CCP Available at an import
    #: anchor's B−1 (db.models.ImportAnchor). Zero everywhere but anchored
    #: budgets; with it the legs still sum to `set_aside`, and the other five
    #: stay post-anchor sums.
    opening: Decimal
    #: What is riding uncovered on this card, lifetime. Distinct from
    #: `uncovered`, which is what the card OWES beyond its reserve: a card can
    #: carry a ride while owing less than it has reserved.
    riding: Decimal
    #: The rest of `card_position` beside `uncovered`. A zero
    #: `reserve_discrepancy` means the identity's BOUNDS hold, not that the
    #: reserve is anywhere near the balance — they are allowances, and they
    #: excused both shapes a real budget produced: a reserve several times its
    #: balance, and a reserve below zero on a card still owing thousands. The
    #: row reads these to say which way a card is unusual where the check has
    #: nothing to say. Required, all three.
    over_reserved: Decimal
    short_reserved: Decimal
    #: The card owes nothing and holds your money — the only state "overpaid"
    #: was ever true of. A negative `set_aside` alone is NOT it, and printing
    #: the word on the sign alone is the defect this field exists to end.
    card_credit: Decimal
    #: The viewed month off the card's own ledger. `charged_this_month` and
    #: `paid_this_month` are magnitudes; `debt_change_this_month` is signed,
    #: positive when the debt shrank. Required — every leg above is a lifetime
    #: total, so a client cannot derive a month from them.
    charged_this_month: Decimal
    #: Every credit the ledger took this month; `paid_this_month` is the
    #: paired-transfer subset. Required — a path that forgot it would report
    #: a card's credits as zero, not raise.
    inflows_this_month: Decimal
    paid_this_month: Decimal
    debt_change_this_month: Decimal
    #: Signed net of rows the bank still calls pending. `POSTED` keeps them out
    #: of the three figures above and out of `balance`, so the panel agrees
    #: with the balance and disagrees with the register by exactly this much.
    #: Required — a path that forgets must raise rather than report a silent
    #: agreement that does not hold.
    pending_this_month: Decimal
    #: Which months put riding debt on this card, chronological. The month is
    #: the actionable half: funding an envelope in the month it ended short
    #: retires the ride, funding it the month after does not reach back.
    #: GROSS — `riding` is net of anything an assignment has since retired,
    #: and retirement is recorded against the assignment's month, not the
    #: month that rode. The client orders and caps for display, and names the
    #: difference rather than implying every month listed is still owed.
    rode_by_month: list[RodeMonth]
    #: `overspent_this_month`, broken out by the envelope that rode. Required,
    #: not optional: a listing path that forgot it would report a card's ridden
    #: month as having come from nowhere.
    overspent_by_category: list[RodeCategory]

    @classmethod
    def from_status(cls, card: Any) -> "CardStatusOut":
        """Serialize one `BudgetService.CardStatus`.

        Here rather than at the endpoint: the field list and the mapping onto
        it are one thing, and a 25-field hand-written literal at a call site is
        where a newly served field gets forgotten by the second listing path.
        """
        return cls(
            account_id=card.account_id,
            name=card.name,
            category_id=card.category_id,
            balance=card.balance,
            set_aside=card.set_aside,
            uncovered=card.uncovered,
            is_closed=card.is_closed,
            overspent_this_month=card.overspent_this_month,
            reserve_discrepancy=card.reserve_discrepancy,
            assigned=card.assigned,
            reserved=card.reserved,
            released=card.released,
            residual=card.residual,
            payments=card.payments,
            opening=card.opening,
            riding=card.riding,
            over_reserved=card.over_reserved,
            short_reserved=card.short_reserved,
            card_credit=card.card_credit,
            charged_this_month=card.charged_this_month,
            inflows_this_month=card.inflows_this_month,
            paid_this_month=card.paid_this_month,
            debt_change_this_month=card.debt_change_this_month,
            pending_this_month=card.pending_this_month,
            rode_by_month=[RodeMonth(month=m, amount=v) for m, v in card.rode_by_month],
            overspent_by_category=[
                RodeCategory(
                    category_id=r.category_id, category_name=r.category_name, amount=r.amount
                )
                for r in card.overspent_by_category
            ],
        )


class CardTimelineMonthOut(ApiModel):
    """One month of a card's reserve — the legs' deltas and the running
    totals once the month had happened (`domain/card_timeline.py`). Leg names
    match `CardStatusOut`'s lifetime totals so the panel and the timeline
    speak one vocabulary. `opening` is non-zero on exactly one row of an
    anchored budget's card: the B−1 seam, the timeline's first entry."""

    month: datetime.date
    opening: Decimal
    assigned: Decimal
    reserved: Decimal
    released: Decimal
    residual: Decimal
    payments: Decimal
    #: What this month did to the reserve, signed — served so the client
    #: ranks rather than re-deriving the legs' arithmetic.
    reserve_delta: Decimal
    #: Cumulative through this month, unfloored.
    set_aside: Decimal
    #: The card's ledger through this month. Negative is owed.
    balance: Decimal
    riding: Decimal
    #: `card_position` at THIS month's reserve and THIS month's balance —
    #: a position against today's balance would be a different (wrong) claim.
    uncovered: Decimal
    over_reserved: Decimal
    short_reserved: Decimal
    card_credit: Decimal


class CardBreachLegOut(ApiModel):
    """One leg's signed contribution to the reserve in the breach month."""

    leg: str
    amount: Decimal


class CardTimelineBreachOut(ApiModel):
    """The first month the reserve crossed below zero, legs ranked most
    negative first — the first entry is what did it."""

    month: datetime.date
    set_aside_before: Decimal
    set_aside_after: Decimal
    legs: list[CardBreachLegOut]


class CardTimelineResponse(ApiModel):
    """A card's whole reserve history, served — never summed client-side."""

    account_id: uuid.UUID
    name: str
    months: list[CardTimelineMonthOut]
    breach: CardTimelineBreachOut | None
    #: B when the budget was anchored at import — the months list then opens
    #: at B−1 with the seam row. Null on unanchored budgets.
    anchor_month: datetime.date | None


class BudgetMonthResponse(ApiModel):
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
    #: `total_overspent` split by what funded it. `total_overspent` is the
    #: headline and the figure every call to action reads — Cover Overspending
    #: funds both parts, and the split says only where the money lands: the
    #: cash part stays in the envelope, the credit part moves into a card's
    #: set-aside and retires the debt riding there.
    #:
    #: The hero chip read `total_overspent_cash` until 2026-09-05, which made
    #: it vanish after a cover while the grid still drew red envelopes.
    #:
    #: Required for the same reason `overspent_count` is: a default would let a
    #: path that forgets report half the story as the whole one.
    total_overspent_cash: Decimal
    total_overspent_credit: Decimal
    #: How many of `overspent_count` carry a cash shortfall. A breakdown, not
    #: a workload: Cover Overspending lists every red envelope.
    overspent_count_cash: int
    # Committed to months after this one; already deducted from to_be_assigned
    assigned_in_future: Decimal = Decimal("0")
    #: B, the first month this budget's envelope math re-derives — set only on
    #: budgets anchored at import (db.models.ImportAnchor). The client clamps
    #: month navigation here; months before it live in the register and
    #: reports only.
    anchor_month: datetime.date | None = None
    category_balances: list[CategoryBalance]
    #: The budget's cards — balance / set aside / uncovered (domain/cards.py).
    #: Empty when the budget has none; the budget page draws its cards
    #: section from exactly this, computing nothing.
    cards: list[CardStatusOut] = []


class AssignmentUpdate(ApiModel):
    amount: Money


class FutureOverspendItem(ApiModel):
    """One (category, month, delta) probe: the signed amount change a pending
    transaction edit would apply — outflow negative, reversals positive."""

    category_id: uuid.UUID
    date: datetime.date
    amount_delta: Money


class FutureOverspendPreviewRequest(ApiModel):
    items: list[FutureOverspendItem]


class FutureOverspendWarningOut(ApiModel):
    category_id: uuid.UUID
    category_name: str
    month: datetime.date
    available_before: Decimal
    available_after: Decimal


class FutureOverspendPreviewResponse(ApiModel):
    warnings: list[FutureOverspendWarningOut]


class MoveMoneyRequest(ApiModel):
    """Move money between envelopes; a null side means To-Be-Assigned."""

    from_category_id: uuid.UUID | None = None
    to_category_id: uuid.UUID | None = None
    amount: Money
    month: datetime.date


class BudgetMoveResponse(ApiModel):
    id: uuid.UUID
    month: datetime.date
    from_category_id: uuid.UUID | None
    to_category_id: uuid.UUID | None
    amount: Decimal
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class CategoryHistoryResponse(ApiModel):
    category_id: uuid.UUID
    last_month_assigned: Decimal
    last_month_spent: Decimal
    average_assigned: Decimal
    average_spent: Decimal
    months_included: int


class CategoryHistoryBatchRequest(ApiModel):
    category_ids: list[uuid.UUID]


class AutoAssignRequest(ApiModel):
    category_ids: list[uuid.UUID]
    action: str
    month: datetime.date


class CoverOverspentPreviewItem(ApiModel):
    category_id: uuid.UUID
    category_name: str
    #: The whole red on this row — cash and card-ridden alike.
    overspent: Decimal
    proposed_addition: Decimal
    #: Still short afterwards. Zero means the grid cell goes black.
    remaining_after: Decimal
    #: How much of this row's red rode onto a card. Covering it retires that
    #: debt instead of leaving spendable money in the envelope, which is worth
    #: saying — required, not optional, so no path can quietly stop saying it.
    credit_overspent: Decimal


class CoverOverspentPreviewResponse(ApiModel):
    items: list[CoverOverspentPreviewItem]
    #: What `items` sums to: the grid's whole red.
    total_overspent: Decimal
    #: How much of that rode onto a card — covered too, and named because the
    #: money lands in the card's set-aside rather than staying spendable.
    total_overspent_credit: Decimal
    total_addition: Decimal
    tba_before: Decimal
    tba_after: Decimal


class CoverOverspentApplyItem(ApiModel):
    category_id: uuid.UUID
    proposed_addition: Money


class CoverOverspentApplyRequest(ApiModel):
    month: datetime.date
    items: list[CoverOverspentApplyItem]


class AssignStrategyTotal(ApiModel):
    strategy: str
    total_amount: Decimal
    total_needed: Decimal | None = None
    to_assign: Decimal
    to_return: Decimal
    affected_count: int


class AssignStrategyTotalsResponse(ApiModel):
    month: datetime.date
    tba: Decimal
    #: The whole red — what the Cover Overspending row shows, and the same
    #: figure the hero chip and the cover dialog use.
    total_overspent: Decimal
    #: How much of that rode onto a card. Covered too; named because the money
    #: lands in a card's set-aside rather than staying spendable.
    total_overspent_credit: Decimal
    strategies: list[AssignStrategyTotal]


class AssignPreviewItemOut(ApiModel):
    category_id: uuid.UUID
    category_name: str
    current_assigned: Decimal
    delta: Decimal
    new_assigned: Decimal


class AssignPreviewResponse(ApiModel):
    strategy: str
    items: list[AssignPreviewItemOut]
    total_needed: Decimal | None = None
    to_assign: Decimal
    to_return: Decimal
    tba_before: Decimal
    tba_after: Decimal
    #: Envelopes this strategy would leave newly in the red, and by how much.
    #: The history strategies SET assigned to a past figure and Reset Assigned
    #: zeroes it, so money already spent can stop being funded — legitimate,
    #: and the one consequence a table of assigned-before/assigned-after does
    #: not show. Required, so a preview cannot quietly stop saying it.
    newly_overspent_count: int
    newly_overspent_total: Decimal


class AssignApplyRequest(ApiModel):
    month: datetime.date
    strategy: str


class AssignApplyResponse(ApiModel):
    to_assign: Decimal
    to_return: Decimal
    categories_changed: int
    tba_after: Decimal
    # Change-log batch for undo; null when the strategy moved nothing
    batch_id: uuid.UUID | None = None


class CoverOverspentApplyResponse(ApiModel):
    batch_id: uuid.UUID | None = None


class RecentPayeeResponse(ApiModel):
    """Most recent payee used in a category — powers add-transaction prefill."""

    payee_id: uuid.UUID
    name: str


# ─── Category classification ─────────────────────────────────────────────────


class CategoryClassSlice(ApiModel):
    activity_class: str
    label: str
    total: Decimal
    count: int


class CategoryClassification(ApiModel):
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
