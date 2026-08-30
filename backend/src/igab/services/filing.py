"""Where a transaction leg may be filed — enforced, not merely unoffered.

`IS_CATEGORIZABLE` (repositories/category_filters.py) is the rule. Until this
module it was honoured only by the pickers: `TransactionEditor`,
`SplitTransactionEditor`, `QuickAddSheet`, `ScheduledTransactionEditor` and
`TransactionRow` each filter on the served `is_categorizable`, and the server
checked nothing but `require_not_card_envelope`. So the rule held exactly as
long as every client surface remembered it, and a row could be filed into an
archived envelope by any other route.

`card_payment.py`'s docstring already stated the principle this module exists
to satisfy — *a rule the server does not enforce is one client away from coming
back* — and then enforced only its own third of it. This is the whole rule, in
the one place, reading the same expression the pickers read.

**Write-time only.** History filed to a category that has since been archived
stays exactly where it is: preserving it is the entire point of archiving
rather than deleting, and every report still counts it
(`category_filters.SPENT_ENVELOPE`). Rows already sitting somewhere they could
not be filed today are a hygiene finding, not an error.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category
from igab.domain.exceptions import InvariantViolation
from igab.repositories.category_filters import IS_CATEGORIZABLE, LIVE_CATEGORY


async def _filing_row(session: AsyncSession, category_id: uuid.UUID) -> Any:
    """The one query behind both the refusal and the question below."""
    return (
        await session.execute(
            select(
                Category.linked_account_id,
                Category.linked_liability_id,
                IS_CATEGORIZABLE.label("categorizable"),
                LIVE_CATEGORY.label("live"),
            ).where(Category.id == category_id)
        )
    ).first()


async def may_be_filed_to(session: AsyncSession, category_id: uuid.UUID | None) -> bool:
    """`IS_CATEGORIZABLE` asked as a question rather than enforced as a refusal.

    Auto-categorization resolves a category *after* the caller's has been
    validated, so it needs the same rule with a different answer shape: an
    inherited category that may not be filed to is dropped and the row lands
    uncategorized, where a hand-picked one raises. Re-checking the terms in
    Python here is how the inherited path and the typed path come to disagree
    about where money may go.

    Liveness is part of the question on this path and not on the other one:
    `require_categorizable` sits behind `require_in_budget`, which rejects an
    id that resolves to nothing, while a payee's stored default can outlive
    the envelope it points at.
    """
    if category_id is None:
        return False
    row = await _filing_row(session, category_id)
    return row is not None and bool(row.categorizable) and bool(row.live)


async def require_categorizable(session: AsyncSession, category_id: uuid.UUID | None) -> None:
    """Refuse a leg filed where `IS_CATEGORIZABLE` says it may not go.

    A no-op for `None` and for every ordinary envelope, so it sits beside
    `require_in_budget` at the same three call sites: create, update (bulk
    categorize included) and split lines.

    A missing category is `require_in_budget`'s to report, not this one's —
    two errors for one cause reads as two problems.

    The message names the actual reason. "That category cannot be used" sends
    someone hunting; a card envelope, a debt envelope and an archived envelope
    are three different situations with three different next actions.
    """
    if category_id is None:
        return
    row = await _filing_row(session, category_id)
    if row is None or row.categorizable:
        return
    if row.linked_account_id is not None:
        raise InvariantViolation(
            "That category is a credit card's payment envelope. Nothing can be filed to it — "
            "assign money to the card in the budget's Credit cards section instead"
        )
    if row.linked_liability_id is not None:
        raise InvariantViolation(
            "That category belongs to a tracked debt. Its activity comes from the loan's "
            "own transfers and interest, not from rows filed into it"
        )
    raise InvariantViolation(
        "That category is archived. Restore it first, or file this to a live category — "
        "its existing history stays where it is either way"
    )
