"""Budget-scoped ownership checks for body-supplied foreign keys.

Route-level dependency guards (`BudgetAccess`, `CategoryAccess`, …) protect the
IDs that appear in the URL path, but IDs supplied in a request *body*
(`category_id`, `payee_id`, `transfer_account_id`, `target_id`, …) bypass those
guards. Persisting such an ID without checking it belongs to the caller's budget
would let one budget reference — or write into — another budget's objects. Call
`require_in_budget` before persisting any body-supplied budget-scoped id.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.domain.exceptions import InvariantViolation


async def require_in_budget(
    session: AsyncSession,
    model: Any,
    id_value: uuid.UUID | None,
    budget_id: uuid.UUID,
    label: str,
) -> None:
    """Verify a budget-scoped object belongs to ``budget_id``.

    No-op when ``id_value`` is ``None``. Raises :class:`InvariantViolation`
    (mapped to HTTP 400 by the API layer) when the object does not exist or
    belongs to a different budget.
    """
    if id_value is None:
        return
    result = await session.execute(
        select(model.id).where(model.id == id_value, model.budget_id == budget_id)
    )
    if result.scalar_one_or_none() is None:
        raise InvariantViolation(f"{label} does not belong to this budget")
