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

from sqlalchemy import Boolean, and_, func, not_, or_, select
from sqlalchemy.orm import aliased

from igab.db.models import Account, Payee, Transaction

NOT_DELETED = Transaction.is_deleted == False  # noqa: E712
POSTED = Transaction.cleared != "pending"
LEAF = Transaction.is_split == False  # noqa: E712
PARENT_ROW = Transaction.parent_transaction_id.is_(None)

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
UNPAIRED_TRANSFER_LEG = and_(TRANSFER_PAYEE, Transaction.transfer_id.is_(None))


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
