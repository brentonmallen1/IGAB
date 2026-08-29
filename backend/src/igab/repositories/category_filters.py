"""Shared category predicates — which envelopes a given surface may offer.

The counterpart to `txn_filters.py`, for categories rather than transactions.

There is not one rule here but two, and conflating them is the mistake the six
client-side spellings made. They differ on system groups, and the difference is
load-bearing:

- `IS_ASSIGNABLE` — money may be budgeted or moved into this envelope. System
  groups are excluded: the seeded system group holds Ready-to-Assign-shaped
  categories, and offering them in a move-money picker is offering to assign
  money to the place money comes from.
- `IS_CATEGORIZABLE` — a transaction leg may be filed here. System groups stay
  IN, because the seeded system group is named `Income` (see
  `api/v1/budgets.py`) and income rows are filed into it. Excluding system
  groups here — which three of the six client spellings effectively did —
  would remove the only place a paycheque can go.

Both exclude hidden categories. `IS_CATEGORIZABLE` also excludes categories
linked to an account or a liability: those are credit-card payment and debt
categories, whose activity is maintained by the transfer and the loan, not by
filing a row into them. `IS_ASSIGNABLE` keeps both — money really is budgeted
into a card's set-aside and into a debt envelope — and what keeps a card
envelope out of the pickers is its hidden group, not this flag.

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
"""

from sqlalchemy import and_, not_, or_, select

from igab.db.models import Category, CategoryGroup

NOT_HIDDEN = Category.is_hidden == False  # noqa: E712

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

#: Money may be budgeted or moved into this envelope.
#:
#: Deliberately does NOT exclude `LINKED_TO_CARD`, though no picker offers a
#: card envelope: money genuinely is assigned to one — that is how a card is
#: paid down — and `ensure_payment_category` puts it in a hidden group, which
#: is what keeps it out of the pickers. Excluding it here would also stop the
#: auto-assign strategies from ever funding a card's paydown target, which is
#: the one thing that target is for. Pinned by
#: `test_a_linked_payment_category_may_be_assigned_but_not_filed`.
IS_ASSIGNABLE = and_(NOT_HIDDEN, not_(IN_HIDDEN_GROUP), not_(IN_SYSTEM_GROUP))

#: A transaction leg may be filed here. System groups stay in — that is where
#: income goes.
IS_CATEGORIZABLE = and_(NOT_HIDDEN, not_(IN_HIDDEN_GROUP), not_(LINKED))

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
