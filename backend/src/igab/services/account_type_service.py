"""Account-type registry: resolution, derivation, and per-budget seeding.

The account_types table is the source of truth for what an account IS — its
label, asset/liability classification, and default budget participation.
accounts.account_type (the type row's key) and accounts.classification are
denormalized mirrors kept so sidebar and report queries stay join-free; the
`apply_type` helper here is their only legitimate writer. Every account
creation or type change must go through resolve_type + apply_type.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import AccountType
from igab.domain.account_types import BUILTIN_ACCOUNT_TYPES
from igab.domain.exceptions import NotFoundError


async def resolve_type(session: AsyncSession, budget_id: uuid.UUID, key: str) -> AccountType:
    """The budget's type row for `key`; NotFoundError for unknown keys."""
    result = await session.execute(
        select(AccountType).where(AccountType.budget_id == budget_id, AccountType.key == key)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("account_type", key)
    return row


def apply_type(type_row: AccountType, on_budget: bool | None = None) -> dict[str, Any]:
    """Account field values the type dictates: an explicit on_budget wins over
    the type's default; classification always follows the type."""
    return {
        "account_type_id": type_row.id,
        "account_type": type_row.key,
        "classification": type_row.classification,
        "on_budget": type_row.default_on_budget if on_budget is None else on_budget,
    }


async def ensure_account_types_seeded(session: AsyncSession, budget_id: uuid.UUID) -> None:
    """Idempotently create any missing built-in type rows for the budget.

    Every budget-creation path must call this — an account cannot be created
    for a budget whose registry is empty.
    """
    existing = await session.execute(
        select(AccountType.key).where(AccountType.budget_id == budget_id)
    )
    present = {key for (key,) in existing}
    for builtin in BUILTIN_ACCOUNT_TYPES:
        if builtin.key not in present:
            session.add(
                AccountType(
                    budget_id=budget_id,
                    key=builtin.key,
                    label=builtin.label,
                    classification=builtin.classification,
                    default_on_budget=builtin.default_on_budget,
                    description=builtin.description,
                    is_system=True,
                    sort_order=builtin.sort_order,
                )
            )
    await session.flush()
