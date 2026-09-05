"""What reconciliation locks on a transaction — and only that.

A reconciled row is one the user has matched against a bank statement. What
that verification vouches for is the money: the amount, the date it moved,
the account it moved in, and the fact that the bank agreed (`cleared`).
Nothing else on the row was on the statement — the category, payee, memo,
split lines and approval flag are the user's bookkeeping, and correcting
bookkeeping must not require unlocking money.

Every guard that asks "may this edit touch a reconciled row?" goes through
`locked_changes`: the service's update path, undo and redo, and the
bank-posting rule (a bank feed never rewrites locked fields either). A
blanket "reconciled rows are immutable" lived in the service before this and
was the bug: a wrong category on a reconciled row could only be fixed by
unreconciling, which the register offered through a 12px lock glyph.

Compare, don't just test membership. The editor PATCHes every field it
shows, so an unchanged amount arriving beside a new memo is not an attempt to
change the amount.
"""

from collections.abc import Iterable, Mapping
from typing import Any

#: The fields a bank statement vouches for. `account_id` is one of them: the
#: statement is an account's statement, so moving a reconciled row out of it
#: changes a balance the user signed off on. It is locked here, once, for
#: every path that can set it — the editor's account picker
#: (`domain.account_move`), undo's restore, and the bank feed.
RECONCILED_LOCKED_FIELDS: frozenset[str] = frozenset({"amount", "date", "cleared", "account_id"})


def locked_changes(current: Mapping[str, Any], proposed: Mapping[str, Any]) -> set[str]:
    """Locked fields whose proposed value differs from the current one.

    Values are compared typed — Decimal to Decimal, date to date — so a
    Numeric round-trip that changed scale ('12.34' vs '12.3400') is not a
    change. Callers holding JSON snapshot values coerce them back to column
    types before asking. A locked field proposed with no current value to
    compare against counts as a change: silence must never unlock money.
    """
    return {
        field
        for field in RECONCILED_LOCKED_FIELDS
        if field in proposed and (field not in current or proposed[field] != current[field])
    }


def locked_values(row: Any) -> dict[str, Any]:
    """The locked fields' current values on a row — an ORM instance or
    anything carrying the same attributes."""
    return {f: getattr(row, f) for f in RECONCILED_LOCKED_FIELDS if hasattr(row, f)}


def reconciled_edit_message(fields: Iterable[str]) -> str:
    """One sentence for every surface that refuses a locked edit."""
    return "This transaction is reconciled — unlock it to change " + ", ".join(sorted(fields))
