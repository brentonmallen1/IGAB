"""Which fields an edit actually changes.

The editor PATCHes every field it shows, so *presence* in the request body
says nothing: an unchanged amount arriving beside a new transfer link is not
an attempt to change the amount. Every guard that refuses an edit because it
"touches" a field has to compare instead of testing membership, and each one
that forgot produced the same bug — a refusal the user could not act on,
because the field they were told to leave alone was one they had not
touched.

Two guards ask this today: `domain.reconciliation` (what a bank statement
vouches for) and the transfer-link rule in `TransactionService.update`
(money and links move in separate edits). One implementation, per CLAUDE.md.
"""

from collections.abc import Iterable, Mapping
from typing import Any


def changed_fields(
    current: Mapping[str, Any], proposed: Mapping[str, Any], fields: Iterable[str]
) -> set[str]:
    """Which of `fields` the proposal would actually change.

    Values are compared typed — Decimal to Decimal, date to date — so a
    Numeric round-trip that changed scale ('12.34' vs '12.3400') is not a
    change. A field proposed with no current value to compare against counts
    as a change: silence must never wave an edit through.
    """
    return {
        field
        for field in fields
        if field in proposed and (field not in current or proposed[field] != current[field])
    }
