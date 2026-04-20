import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from igab.dependencies import CurrentUser, get_account_repo
from igab.domain.exceptions import DuplicateError, NotFoundError
from igab.repositories.account_repo import AccountRepository

router = APIRouter()


@router.get("/{budget_id}/accounts", response_model=list[AccountResponse])
async def list_accounts(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    include_closed: bool = False,
) -> list[AccountResponse]:
    accounts = await account_repo.get_all(budget_id, include_closed=include_closed)
    result = []
    for acc in accounts:
        balance = await account_repo.get_balance(acc.id)
        cleared = await account_repo.get_cleared_balance(acc.id)
        uncategorized = await account_repo.get_uncategorized_count(acc.id)
        resp = AccountResponse.model_validate(acc)
        resp.balance = balance
        resp.cleared_balance = cleared
        resp.uncleared_balance = balance - cleared
        resp.uncategorized_count = uncategorized
        result.append(resp)
    return result


@router.post("/{budget_id}/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    budget_id: uuid.UUID,
    body: AccountCreate,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> AccountResponse:
    # Tracking accounts are always off-budget
    on_budget = body.on_budget
    if body.account_type == "tracking":
        on_budget = False

    try:
        acc = await account_repo.create(
            budget_id=budget_id,
            name=body.name,
            account_type=body.account_type,
            on_budget=on_budget,
            note=body.note,
            sort_order=body.sort_order,
        )
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    resp = AccountResponse.model_validate(acc)
    resp.balance = await account_repo.get_balance(acc.id)
    return resp


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> AccountResponse:
    try:
        acc = await account_repo.get_or_raise(account_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    resp = AccountResponse.model_validate(acc)
    balance = await account_repo.get_balance(acc.id)
    cleared = await account_repo.get_cleared_balance(acc.id)
    resp.balance = balance
    resp.cleared_balance = cleared
    resp.uncleared_balance = balance - cleared
    resp.uncategorized_count = await account_repo.get_uncategorized_count(acc.id)
    return resp


@router.patch("/accounts/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: uuid.UUID,
    body: AccountUpdate,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> AccountResponse:
    try:
        changes = body.model_dump(exclude_none=True)
        acc = await account_repo.update(account_id, **changes)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    resp = AccountResponse.model_validate(acc)
    resp.balance = await account_repo.get_balance(acc.id)
    return resp


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> None:
    try:
        await account_repo.soft_delete(account_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
