"""One session double for the guards every transaction write runs through.

`TransactionService.create/update/_split` call `require_in_budget` and
`require_categorizable` before touching anything, so any unit test that drives
a write has to satisfy both — and three test modules each spelled their own
stub for them. When `require_categorizable` replaced `require_not_card_envelope`
the query shape changed, and all three broke in the same way for the same
reason, which is the argument for there being one of these.

The default answers are "yes, ordinary, file away": the id belongs to the
budget, and the category is a live spending envelope. A test that wants a
refusal should say so explicitly rather than by omission.
"""

from unittest.mock import AsyncMock, MagicMock


def categorizable_row(
    *, categorizable: bool = True, linked_account: bool = False, linked_liability: bool = False
):
    """What `require_categorizable` reads back for one category."""
    row = MagicMock()
    row.categorizable = categorizable
    row.linked_account_id = MagicMock() if linked_account else None
    row.linked_liability_id = MagicMock() if linked_liability else None
    return row


def writable_session(*, category_row=None) -> AsyncMock:
    """An `AsyncMock` session that satisfies the pre-write guards.

    One `execute` serves both: `require_in_budget` reads
    `.scalar_one_or_none()`, `require_categorizable` reads `.first()`.
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=MagicMock())
    result.first = MagicMock(return_value=category_row or categorizable_row())
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.scalar = AsyncMock(return_value=None)
    return session
