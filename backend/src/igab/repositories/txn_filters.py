"""Shared transaction-filter predicates encoding the money-aggregation rules.

Two query shapes exist and must never be mixed up:

- PARENT_ROW: rows that carry account-balance meaning. A split parent's amount
  equals the sum of its children, so account/cash-flow sums use parent rows
  (split children would double-count).
- LEAF: rows that carry category meaning. Categories live on split children
  and plain transactions; split parents have no category. Category-keyed sums
  use leaf rows (a parent row would hide every split's category activity).

POSTED excludes pending bank transactions from every money aggregate: pending
amounts are provisional (auth holds change at posting), so money moves exactly
once — when the transaction posts. This mirrors AccountRepository.get_balance.
"""

from datetime import date

from sqlalchemy import Boolean, and_, func, not_, or_, select
from sqlalchemy.orm import aliased

from igab.db.models import Account, Payee, Tag, Transaction, category_tags, payee_tags

NOT_DELETED = Transaction.is_deleted == False  # noqa: E712
POSTED = Transaction.cleared != "pending"
LEAF = Transaction.is_split == False  # noqa: E712
PARENT_ROW = Transaction.parent_transaction_id.is_(None)

#: Rows that carry account-balance meaning. Composed rather than respelled:
#: every balance sum in the app wants exactly these three, and spelling them
#: by hand is how `get_balance` and the guide's `_account_balance` came to
#: disagree about whether a pending auth hold is money.
BALANCE_ROW = and_(NOT_DELETED, PARENT_ROW, POSTED)

#: The bank has confirmed this row. Implies POSTED — 'pending' is not in the
#: set — but the two are kept separate because they answer different
#: questions: POSTED is "has this moved", CLEARED is "has the bank agreed".
CLEARED = Transaction.cleared.in_(("cleared", "reconciled"))

#: Bank-identity states of a row, for the sync's candidate search.
#:
#: BANK_UNLINKED — no bank id at all: a YNAB/CSV import or a hand-typed row.
#:
#: PROVISIONALLY_LINKED — carries a bank id, but the bank has not posted
#: against it yet (`bank_posted_date` is NULL): either a pending row the sync
#: created, or a user row matched while the bank record was still an auth
#: hold. A bank that re-identifies the record at posting reports a "new"
#: posted record whose only existing counterpart is one of these — so a
#: posted feed record may claim them (same amount, the usual date rules); a
#: pending feed record never may.
#:
#: The `cleared` guard is load-bearing. Rows linked before `bank_posted_date`
#: existed are `cleared` with a NULL posted date; without the guard every one
#: of them could absorb a foreign same-amount bank id.
BANK_UNLINKED = Transaction.sync_id.is_(None)
PROVISIONALLY_LINKED = and_(
    Transaction.sync_id.isnot(None),
    Transaction.bank_posted_date.is_(None),
    Transaction.cleared.in_(("pending", "uncleared")),
)

#: A row the user (or their file import) wrote and no bank feed has touched —
#: what the review-queue matcher pairs a freshly synced row against.
#: `sync_id` alone misses id-less feeds: a sync-created row without a bank id
#: is still bank-sourced, never a "manual" match candidate.
USER_ENTERED = and_(
    Transaction.import_id.is_(None),
    Transaction.sync_id.is_(None),
    Transaction.sync_source.is_(None),
    Transaction.linked_transaction_id.is_(None),
)


def sync_created_pending(source: str):
    """A pending row the named feed itself wrote. Never a user row: only
    the sync sets `pending`, and it always stamps its source."""
    return and_(
        Transaction.cleared == "pending",
        Transaction.sync_source == source,
        Transaction.sync_id.isnot(None),
    )


def not_future(as_of: date):
    """Rows dated on or before `as_of`.

    A function, not a constant: a module-level `Transaction.date <= today()`
    would freeze the date at import time and quietly go stale in a
    long-running process.

    **This is deliberately NOT part of CLEARED, and the two callers of
    CLEARED differ by exactly this predicate.** They are asking different
    questions, and forcing them into agreement would break one of them:

    - The account header reports a partition — `balance`, `cleared_balance`
      and `uncleared_balance`, where the first is the sum of the other two.
      Applying a cutoff to only one term does not remove a future-dated
      cleared row from the header; it relabels it as *uncleared*, which is a
      worse answer than the one it replaced. Applying it to all three hides
      a transaction the register plainly shows.
    - Reconciliation asks what today's bank statement should say, and a
      statement cannot reflect what has not happened. `get_status` therefore
      adds this cutoff, and `finish()` sizes its adjustment against the
      result — so the adjustment is correct even while the header differs.

    The divergence is bounded to exactly the future-dated cleared rows, and
    is pinned by a test. Do not "fix" it into agreement.
    """
    return Transaction.date <= as_of


# A transfer leg, by either of the two signals that mark one. The partner link
# is the strong signal, but it is not always present: a YNAB import writes legs
# whose partner never appears (the partner account was skipped, or the leg's
# categorized counterpart never entered the pairing pool) so that balances stay
# right. Those rows are still transfers, and recognizing them only by
# `transfer_id` counted them as real income or expense.
# EXISTS, not `payee_id IN (subquery)`. `NULL IN (non-empty set)` is UNKNOWN,
# and `NOT UNKNOWN` is UNKNOWN — so the negation below silently dropped every
# payee-less row from every query using it, but only once the budget had at
# least one transfer payee to make the subquery non-empty. EXISTS is two-valued
# and cannot reproduce that.
TRANSFER_PAYEE = (
    select(Payee.id)
    .where(Payee.id == Transaction.payee_id, Payee.transfer_account_id.isnot(None))
    .correlate(Transaction)
    .exists()
)
TRANSFER_LEG = or_(Transaction.transfer_id.isnot(None), TRANSFER_PAYEE)
NON_TRANSFER = ~TRANSFER_LEG

_partner = aliased(Transaction)

#: The account on the other side of a transfer. The partner link is the strong
#: signal; an orphaned leg falls back to the account its transfer payee names,
#: the same signal TRANSFER_LEG uses to recognise it at all.
#
# `.correlate(Transaction)` is load-bearing. These nest inside another scalar
# subquery whose FROM is `accounts`, and SQLAlchemy only auto-correlates
# against the immediately enclosing SELECT — without it the planner adds
# `transactions` to the inner FROM and the subquery cross-joins.
COUNTERPART_ACCOUNT_ID = func.coalesce(
    select(_partner.account_id)
    .where(_partner.id == Transaction.transfer_id)
    .correlate(Transaction)
    .scalar_subquery(),
    select(Payee.transfer_account_id)
    .where(Payee.id == Transaction.payee_id)
    .correlate(Transaction)
    .scalar_subquery(),
)

#: Does this transfer leg point out of the budget? Coalesced so an
#: unresolvable counterpart reads as "no" rather than NULL — a NULL here would
#: poison every OR it takes part in, which is the bug TRANSFER_PAYEE just fixed.
_COUNTERPART_ON_BUDGET = func.coalesce(
    select(Account.on_budget)
    .where(Account.id == COUNTERPART_ACCOUNT_ID)
    .correlate(Transaction)
    .scalar_subquery(),
    True,
    type_=Boolean,
)
COUNTERPART_OFF_BUDGET = not_(_COUNTERPART_ON_BUDGET)

# Cash-flow rows: plain transactions, categorized transfer legs (YNAB spending
# transfers), and any leg pointing OUT of the budget. That last case is money
# genuinely leaving: a transfer to a brokerage or a mortgage is not internal
# movement just because the user left it uncategorized, and excluding it made
# the saving it represents invisible to every cash-flow report.
#
# Transfers between two on-budget accounts stay out — both legs sit inside the
# budget, so counting either double-counts. That asymmetry is the point: only
# the on-budget leg of an out-of-budget transfer passes, never the tracked side.
CASH_FLOW_ROW = or_(~TRANSFER_LEG, Transaction.category_id.isnot(None), COUNTERPART_OFF_BUDGET)
# Budget cash flow happens on on-budget accounts: plain activity inside
# tracking accounts (dividends, market adjustments, loan interest) moves net
# worth, not budget income/expense. Categorized spending-transfer legs already
# live on the on-budget side (service-enforced), so they pass. Reports that
# take an explicit account filter let the user's selection override this.
ON_BUDGET_ACCOUNT = Transaction.account_id.in_(
    select(Account.id).where(Account.on_budget == True)  # noqa: E712
)


#: A transfer leg whose partner never arrived: the payee names another account,
#: but no row links back. Balances stay right — both sides were written — but
#: nothing marks the row as internal movement, so reports read it as real
#: income or spending until someone disbelieves a chart.
#:
#: A YNAB import produces these in bulk when an account is left out: the far
#: leg is never created, so there is nothing to pair with. One real import
#: made 1,117.
#:
#: Note this is NOT the existing `is_transfer` filter, which tests
#: `transfer_id` alone — `is_transfer=false` returns every ordinary
#: transaction as well as these.
#:
#: `category_id IS NULL` is the third condition and it is load-bearing. A
#: *categorized* transfer leg is a YNAB spending transfer: deliberately
#: unpaired, and correctly counted as spending because the category is the
#: whole point. The importer knows this — it only ever tries to pair
#: uncategorized legs (`importer.py`: `payee.startswith("Transfer : ") and
#: category_id is None`) — so without this condition the predicate counts 169
#: rows on a real export that the importer does not, and the hygiene panel
#: promises a number the list it links to cannot show. Same definition, both
#: sides; asserted against a real import in test_ynab_import.py.
UNPAIRED_TRANSFER_LEG = and_(
    TRANSFER_PAYEE,
    Transaction.transfer_id.is_(None),
    Transaction.category_id.is_(None),
)


#: A row the user still has to file: no category, and it is the kind of row a
#: category is *for*.
#:
#: The three exclusions all matter, and each was wrong somewhere before this
#: existed:
#:
#: - `LEAF` — a split parent carries no category by design; its legs do.
#: - `ON_BUDGET_ACCOUNT` — off-budget rows (market movement, payroll
#:   contributions, loan interest) are net-worth movement, not spending
#:   awaiting a category.
#: - `CASH_FLOW_ROW` — the load-bearing one. Testing `transfer_id IS NULL`
#:   instead recognises only a *linked* transfer, so a leg whose partner never
#:   turned up (a skipped account, an unmatched pair) was counted as needing a
#:   category. A real YNAB import produced 1,117 of those. `CASH_FLOW_ROW`
#:   reads TRANSFER_LEG, which knows a transfer by its payee as well as its
#:   link — and it keeps the case that genuinely does need one: a transfer to
#:   an OFF-budget account is a mortgage payment, and budgeting for it is the
#:   whole point.
#:
#: Stated as an invariant: **needs a category** agrees with **counts as budget
#: cash flow**. A row that does not count cannot need one; a row that counts
#: and has none, does. `CASH_FLOW_ROW`'s middle arm (`category_id IS NOT NULL`)
#: is dead here because of the first condition, so the two compose exactly.
#: POSTED is deliberately NOT part of this. Whether a category applies to a row
#: is a fact about the row; whether it is *work the user can do now* is a
#: question the caller asks. Counters (the badge, the per-account count) add
#: POSTED because a pending amount is provisional and often arrives with its
#: payee. The Uncategorized filter does not, because a filter shows rows that
#: match rather than tallying a workload. That divergence is intended, is
#: bounded to exactly the pending uncategorized rows, and is pinned by a test —
#: do not "fix" it into agreement.
NEEDS_CATEGORY = and_(
    Transaction.category_id.is_(None),
    LEAF,
    ON_BUDGET_ACCOUNT,
    CASH_FLOW_ROW,
)


# ─── Tags on the row's category or payee ─────────────────────────────────────
#
# Both are guarded by the NOT NULL test: `NULL IN (...)` is UNKNOWN, not FALSE,
# and a CASE arm evaluating to UNKNOWN differs from one evaluating FALSE only
# by luck of ordering. Keep every arm two-valued. `category_tagged` is what
# the activity classifier reads for the savings and debt tags; it lived there
# as `_tagged` until the essentials report needed the same shape.


def _tag_ids(system_keys: tuple[str, ...]):
    return select(Tag.id).where(
        Tag.system_key.in_(system_keys),
        Tag.is_deleted == False,  # noqa: E712
    )


def category_tagged(*system_keys: str):
    """Rows whose category carries any of these system tags."""
    return and_(
        Transaction.category_id.isnot(None),
        Transaction.category_id.in_(
            select(category_tags.c.category_id).where(
                category_tags.c.tag_id.in_(_tag_ids(system_keys))
            )
        ),
    )


def payee_tagged(*system_keys: str):
    """Rows whose payee carries any of these system tags."""
    return and_(
        Transaction.payee_id.isnot(None),
        Transaction.payee_id.in_(
            select(payee_tags.c.payee_id).where(payee_tags.c.tag_id.in_(_tag_ids(system_keys)))
        ),
    )


#: Spending the household could not do without: the category OR the payee is
#: tagged Essential. Evaluated only by TransactionRepository.essential_spend*
#: — the Guide, the Overview card and the Essentials report all read those.
ESSENTIAL_TAGGED = or_(category_tagged("essential"), payee_tagged("essential"))
