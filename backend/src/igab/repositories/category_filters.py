"""Shared category predicates — which envelopes a given surface may offer.

The counterpart to `txn_filters.py`, for categories rather than transactions.

Two of these answer "which envelopes may a surface offer", and conflating them
is the mistake the six client-side spellings made. They differ on system groups,
and the difference is load-bearing:

- `IS_ASSIGNABLE` — a picker may OFFER this envelope. System groups are
  excluded: the seeded system group holds Ready-to-Assign-shaped categories,
  and offering them in a move-money picker is offering to assign money to the
  place money comes from. Card envelopes are excluded too — the cards section
  is their only face.
- `IS_FUNDABLE` — money may ENTER this envelope. A different question, which is
  the whole reason it is a separate constant: a card envelope is funded but
  never offered. Read by `assign_service` and by the money-moving endpoints.
- `IS_CATEGORIZABLE` — a transaction leg may be filed here. System groups stay
  IN, because the seeded system group is named `Income` (see
  `api/v1/budgets.py`) and income rows are filed into it. Excluding system
  groups here — which three of the six client spellings effectively did —
  would remove the only place a paycheque can go.

Both exclude hidden categories. `IS_CATEGORIZABLE` also excludes categories
linked to an account or a liability: those are credit-card payment and debt
categories, whose activity is maintained by the transfer and the loan, not by
filing a row into them. `IS_FUNDABLE` keeps both — money really is budgeted
into a card's set-aside and into a debt envelope — while `IS_ASSIGNABLE` names
the card envelope outright instead of leaning on its group being hidden, which
was a coincidence rather than a rule.

**Why these are served rather than computed on the client.** `is_hidden` is on
the category row, so it looks like the client has everything it needs. It does
not, twice over:

- `CategoryResponse` did not expose `linked_liability_id`, so the
  liability-binding screen could not express its own rule and offered
  categories another liability already owned.
- `CategoryRepository.get_all(include_hidden=False)` filters the *category's*
  `is_hidden`, not the *group's*, while `CategoryGroupRepository.get_all`
  filters the group's. So a hidden group's categories arrive at the client
  while the group does not: they leaked into the pickers that build a
  system-group set from the group list, and silently vanished from the pickers
  that group by `!g.is_hidden`.

Both flags read the group, which changes without the category row being
touched — the same reason `needs_category` cannot be a column.

`SPENDABLE` further down answers a different question — whose money can come
back on a credit card — and is deliberately not an offering rule; see its own
comment for why hidden categories stay in it.
"""

from sqlalchemy import and_, not_, or_, select

from igab.db.models import Category, CategoryGroup

NOT_HIDDEN = Category.is_hidden == False  # noqa: E712
#: A category the arithmetic may still see. Soft-delete only: a *hidden*
#: category is live — it still holds money and can still overspend.
LIVE_CATEGORY = Category.is_deleted == False  # noqa: E712

#: Does this category's group belong to the budget's system arrangement?
#: EXISTS rather than `category_group_id IN (subquery)`: `NULL IN (non-empty
#: set)` is UNKNOWN and `NOT UNKNOWN` is UNKNOWN, which would silently drop
#: rows from the negation. The same trap `TRANSFER_PAYEE` documents.
IN_SYSTEM_GROUP = (
    select(CategoryGroup.id)
    .where(
        CategoryGroup.id == Category.category_group_id,
        CategoryGroup.is_system == True,  # noqa: E712
    )
    .correlate(Category)
    .exists()
)

#: The group itself is hidden. A category in a hidden group is not offered
#: anywhere, whatever its own flag says.
IN_HIDDEN_GROUP = (
    select(CategoryGroup.id)
    .where(
        CategoryGroup.id == Category.category_group_id,
        CategoryGroup.is_hidden == True,  # noqa: E712
    )
    .correlate(Category)
    .exists()
)

#: A card's set-aside envelope, owned by the account rather than by the user.
#: The cards section is its only home: it is drawn there with liability
#: columns (Balance / Ready to pay / Uncovered), assigned there, and nothing
#: may be filed to it — `get_budget_summary` overwrites its balance from card
#: arithmetic, so a row filed here is money that leaves the budget silently.
LINKED_TO_CARD = Category.linked_account_id.isnot(None)

#: Maintained by something other than the user filing a row: a credit-card
#: payment category, or a debt category owned by a liability.
LINKED = or_(LINKED_TO_CARD, Category.linked_liability_id.isnot(None))

#: **What a picker may OFFER.** Not where money may go — see `IS_FUNDABLE`.
#:
#: These were one rule, and the comment that lived here argued the conflation
#: was deliberate: that `LINKED_TO_CARD` stays in because "excluding it would
#: stop the auto-assign strategies from ever funding a card's paydown target,
#: which is the one thing that target is for". Measured against a card envelope
#: built the way `ensure_payment_category` builds one, that was already false:
#: the envelope lives in a hidden group, so `IN_HIDDEN_GROUP` excluded it
#: anyway, `is_assignable` came back False, and `assign_service` — which
#: filters on exactly this flag — had never once funded a card target. The
#: rule was protecting an outcome it had already lost.
#:
#: So a card envelope is excluded here outright. The cards section is its only
#: face, which is what `card_payment.py` says it is.
IS_ASSIGNABLE = and_(NOT_HIDDEN, not_(IN_HIDDEN_GROUP), not_(IN_SYSTEM_GROUP), not_(LINKED_TO_CARD))

#: **Where money may ENTER.** A strictly different question from what a picker
#: offers, and keeping them apart is what lets a card envelope be funded
#: without being listed.
#:
#: Income is out, always: money assigned to a system-group category would
#: neither reduce Ready to Assign nor ever come back out. Everything else the
#: user can still see is in, and so is a card envelope, however hidden — a card
#: is paid down by assigning to it, and `assign_service` reads this so a
#: paydown target finally fills.
#:
#: **Direction matters, and only for entry.** Money may always LEAVE an
#: envelope — that is how a stranded balance in an archived one gets rescued —
#: so `budget_service` gates the source of a move on income alone and the
#: destination on this. The two used to be one check spelling one of these
#: three terms, under a comment claiming it was "the same rule" as
#: `IS_ASSIGNABLE`.
IS_FUNDABLE = and_(
    not_(IN_SYSTEM_GROUP),
    or_(and_(NOT_HIDDEN, not_(IN_HIDDEN_GROUP)), LINKED_TO_CARD),
)

#: A transaction leg may be filed here. System groups stay in — that is where
#: income goes.
IS_CATEGORIZABLE = and_(NOT_HIDDEN, not_(IN_HIDDEN_GROUP), not_(LINKED))

#: A category whose own money can come back on a card: the envelopes
#: `sum_credit_outflows_by_category` releases against, and so exactly the set
#: whose complement is an inflow the budget has no claim on
#: (`txn_filters.UNBUDGETED_CARD_CREDIT`). **Both sides read this constant.**
#:
#: Not an offering rule, so hidden is not in it: a hidden envelope still holds
#: money and its spending still reserves against a card. `LINKED_TO_CARD` is
#: out because a card's own set-aside is maintained by the arithmetic rather
#: than by a row filed to it — but `linked_liability_id` stays IN, because a
#: debt envelope is an ordinary spending envelope to this question.
#: `IN_SYSTEM_GROUP` is out because income is not a category's money coming
#: back; it is money arriving.
#:
#: Written out separately, this and its complement stopped being complements
#: twice. First over transfers: one side required `NON_TRANSFER` while the
#: other required a *cash* counterpart, so a card paid off from an off-budget
#: account fell into no term and the reserve identity read the whole set-aside
#: as drift. Then over income: the complement was spelled `category_id IS
#: NULL`, so a rewards credit filed to Ready to Assign reduced a card's balance
#: and reached no term at all — permanent, invisible, growing with every such
#: row ("The Watchman's Arithmetic").
SPENDABLE = and_(LIVE_CATEGORY, not_(LINKED_TO_CARD), not_(IN_SYSTEM_GROUP))

#: The two envelope rules the reports ask with. They differ by one term, on
#: purpose, and the difference is stated here because it was previously
#: unstated and had drifted ten ways across ten queries.
#:
#: `report_service` wrote these out by hand at ten call sites and no two
#: clusters agreed. Five queries over assignments: four excluded categories
#: under a soft-deleted group, one did not. Five over spending rows: one
#: excluded them, four did not. So `budget_vs_actual` and `cumulative_variance`
#: gave different answers about the same assignments, and `plan_vs_reality`
#: and `spending_grouped` about the same spending. That is a budgeting app
#: contradicting itself, which is the failure this module exists to prevent.
#:
#: **Neither excludes a soft-deleted GROUP.** A live category under a deleted
#: group is a real, reachable state — `UNDER_DELETED_GROUP` below is the check
#: that reports it — and `get_budget_summary` counts it, because
#: `CategoryRepository.get_all` filters the category's `is_deleted` and not the
#: group's. A report that drops it disagrees with the budget page it reports
#: on, silently and in the shrinking direction. The anomaly gets named by the
#: integrity check and repaired; it does not get hidden by the reports.
#:
#: The one term that differs is the category's own liveness:
#:
#: - **`BUDGETED_ENVELOPE`** — where the budget PLANS money. Excludes a deleted
#:   category, because `get_budget_summary` does, and a plan-vs-actual report
#:   whose plan disagrees with the budget grid is worse than no report.
#: - **`SPENT_ENVELOPE`** — where money WAS spent. Keeps a deleted category:
#:   the money moved, and deleting the envelope afterwards does not unspend it.
#:   Under-reporting spending is the dangerous direction for this app.
#:
#: On the happy path the two agree, which is why the divergence went unnoticed:
#: `CategoryService.delete_categories` calls `_clear_assignments` and
#: `_retarget_transactions`, so a deleted category is left holding neither. The
#: gap opens only on rows an older delete path or an import left behind — and
#: those are exactly the rows a person would notice missing from a total.
#: Pinned by `test_report_envelope_rules.py`, which fails if the gap widens.
BUDGETED_ENVELOPE = and_(LIVE_CATEGORY, not_(IN_SYSTEM_GROUP))
SPENT_ENVELOPE = not_(IN_SYSTEM_GROUP)

#: A group holding nothing but card set-aside envelopes. The budget grid never
#: draws it — every one of its rows belongs to the cards section — so
#: "Credit Card Payments" appears as no header at all, even where hidden groups
#: are deliberately shown.
#:
#: Served (`CategoryGroupResponse.is_card_only`) rather than derived on the
#: client, and read by `CategoryGroupRepository.reorder` as well, because the
#: two had drifted: the grid dropped card-only groups while the reorder rule
#: allowed omitting only hidden or system ones, so dragging a group was refused
#: on any budget that had one. The client also *could not* compute it — its
#: category list filters hidden categories, so a group whose only non-card row
#: is hidden reads as card-only there and not here. This side is right.
#:
#: An empty group is NOT card-only: a group the user just made still needs its
#: header to drop things into.
GROUP_IS_CARD_ONLY = and_(
    select(Category.id)
    .where(Category.category_group_id == CategoryGroup.id, LIVE_CATEGORY)
    .correlate(CategoryGroup)
    .exists(),
    not_(
        select(Category.id)
        .where(
            Category.category_group_id == CategoryGroup.id,
            LIVE_CATEGORY,
            not_(LINKED_TO_CARD),
        )
        .correlate(CategoryGroup)
        .exists()
    ),
)

#: The category is live but its group is soft-deleted: gone from the grid
#: (which renders only the groups it was given) yet still in the budget
#: summary's arithmetic. The integrity check reports these and the repair
#: endpoint counts them — this expression is the one statement of that rule;
#: it was found written out twice, both copies new in the same PR.
UNDER_DELETED_GROUP = (
    select(CategoryGroup.id)
    .where(
        CategoryGroup.id == Category.category_group_id,
        CategoryGroup.is_deleted == True,  # noqa: E712
    )
    .correlate(Category)
    .exists()
)
