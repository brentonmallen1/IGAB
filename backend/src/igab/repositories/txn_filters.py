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

from sqlalchemy import Boolean, func, not_, or_, select
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

# Cash-flow rows: plain transactions plus CATEGORIZED transfer legs (spending
# transfers to off-budget accounts). Uncategorized transfer legs are internal
# money movement and never income/expense — including the orphaned ones, which
# is the whole point of matching on the payee as well as the partner link.
#
# NOTE: an uncategorized transfer *out of the budget* now classifies as savings
# or debt principal (see activity_class RULES), but is still excluded here.
# Admitting it requires cash_flow_sankey to split income from expense by
# activity class rather than by amount sign — otherwise a withdrawal from a
# brokerage (+500 into checking) reads as income. The two changes have to land
# together; until then this stays as it was.
CASH_FLOW_ROW = or_(~TRANSFER_LEG, Transaction.category_id.isnot(None))
# Budget cash flow happens on on-budget accounts: plain activity inside
# tracking accounts (dividends, market adjustments, loan interest) moves net
# worth, not budget income/expense. Categorized spending-transfer legs already
# live on the on-budget side (service-enforced), so they pass. Reports that
# take an explicit account filter let the user's selection override this.
ON_BUDGET_ACCOUNT = Transaction.account_id.in_(
    select(Account.id).where(Account.on_budget == True)  # noqa: E712
)
