import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, update

from igab.api.v1.schemas.account_type import (
    AccountTypeCreate,
    AccountTypeResponse,
    AccountTypeUpdate,
)
from igab.db.models import Account
from igab.dependencies import BudgetAccess, CurrentUser, get_account_type_repo
from igab.domain.exceptions import NotFoundError
from igab.repositories.account_type_repo import AccountTypeRepository

router = APIRouter()

AccountTypeRepoDep = Annotated[AccountTypeRepository, Depends(get_account_type_repo)]


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return slug[:30] or "type"


async def _get_budget_type(repo: AccountTypeRepository, budget_id: uuid.UUID, type_id: uuid.UUID):
    row = await repo.get(type_id)
    if row is None or row.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account type not found")
    return row


@router.get("/{budget_id}/account-types", response_model=list[AccountTypeResponse])
async def list_account_types(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    repo: AccountTypeRepoDep,
) -> list[AccountTypeResponse]:
    rows = await repo.get_all(budget_id)
    return [AccountTypeResponse.model_validate(r) for r in rows]


@router.post(
    "/{budget_id}/account-types",
    response_model=AccountTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_account_type(
    budget_id: BudgetAccess,
    body: AccountTypeCreate,
    current_user: CurrentUser,
    repo: AccountTypeRepoDep,
) -> AccountTypeResponse:
    """Create a custom account type. The key is derived from the label
    (slugified, suffixed on collision) and never changes afterwards — accounts
    reference it, so only the label is editable."""
    base_key = _slugify(body.label)
    key = base_key
    suffix = 2
    while await repo.get_by_key(budget_id, key) is not None:
        key = f"{base_key[: 30 - len(str(suffix)) - 1]}_{suffix}"
        suffix += 1

    row = await repo.create(
        budget_id=budget_id,
        key=key,
        label=body.label,
        classification=body.classification.value,
        default_on_budget=body.default_on_budget,
        description=body.description,
        is_system=False,
    )
    return AccountTypeResponse.model_validate(row)


@router.patch("/{budget_id}/account-types/{type_id}", response_model=AccountTypeResponse)
async def update_account_type(
    budget_id: BudgetAccess,
    type_id: uuid.UUID,
    body: AccountTypeUpdate,
    current_user: CurrentUser,
    repo: AccountTypeRepoDep,
) -> AccountTypeResponse:
    row = await _get_budget_type(repo, budget_id, type_id)
    if row.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Built-in account types cannot be edited",
        )

    changes = body.model_dump(exclude_unset=True)
    if "classification" in changes and changes["classification"] is not None:
        changes["classification"] = changes["classification"].value
    try:
        row = await repo.update(type_id, **changes)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    # classification is mirrored onto accounts — keep every referencing
    # account's mirror in sync with its type row
    if "classification" in changes:
        await repo.session.execute(
            update(Account)
            .where(Account.account_type_id == type_id)
            .values(classification=row.classification, updated_at=func.now())
        )
        await repo.session.flush()

    return AccountTypeResponse.model_validate(row)


@router.delete("/{budget_id}/account-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account_type(
    budget_id: BudgetAccess,
    type_id: uuid.UUID,
    current_user: CurrentUser,
    repo: AccountTypeRepoDep,
) -> None:
    row = await _get_budget_type(repo, budget_id, type_id)
    if row.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Built-in account types cannot be deleted",
        )
    referencing = await repo.account_count(type_id)
    if referencing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{referencing} account(s) still use this type — retype them first",
        )
    await repo.hard_delete(type_id)
