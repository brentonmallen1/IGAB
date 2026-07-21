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

from sqlalchemy import or_

from igab.db.models import Transaction

NOT_DELETED = Transaction.is_deleted == False  # noqa: E712
POSTED = Transaction.cleared != "pending"
LEAF = Transaction.is_split == False  # noqa: E712
PARENT_ROW = Transaction.parent_transaction_id.is_(None)
NON_TRANSFER = Transaction.transfer_id.is_(None)
# Cash-flow rows: plain transactions plus CATEGORIZED transfer legs (spending
# transfers to off-budget accounts). Uncategorized transfer legs are internal
# money movement and never income/expense.
CASH_FLOW_ROW = or_(Transaction.transfer_id.is_(None), Transaction.category_id.isnot(None))
