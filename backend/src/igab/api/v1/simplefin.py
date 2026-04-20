import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.simplefin import (
    LinkSimpleFINRequest,
    SimpleFINConnectionResponse,
    SimpleFINSetupRequest,
    SimpleFINUpdateRequest,
    SyncResult,
)
from igab.dependencies import CurrentUser, get_account_repo, get_simplefin_service
from igab.repositories.account_repo import AccountRepository
from igab.services.simplefin_service import SimpleFINService

router = APIRouter()


@router.post("/simplefin/setup", response_model=SimpleFINConnectionResponse, status_code=201)
async def setup_simplefin(
    body: SimpleFINSetupRequest,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> SimpleFINConnectionResponse:
    try:
        conn = await svc.setup(current_user.id, body.setup_token)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return SimpleFINConnectionResponse.model_validate(conn)


@router.get("/simplefin/connections", response_model=list[SimpleFINConnectionResponse])
async def list_connections(
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> list[SimpleFINConnectionResponse]:
    conns = await svc.list_connections(current_user.id)
    return [SimpleFINConnectionResponse.model_validate(c) for c in conns]


@router.put("/simplefin/connections/{connection_id}", response_model=SimpleFINConnectionResponse)
async def update_connection(
    connection_id: uuid.UUID,
    body: SimpleFINUpdateRequest,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> SimpleFINConnectionResponse:
    conn = await svc.update_interval(connection_id, body.sync_interval_hours)
    return SimpleFINConnectionResponse.model_validate(conn)


@router.delete("/simplefin/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> None:
    await svc.delete(connection_id)


@router.get("/simplefin/connections/{connection_id}/accounts")
async def get_remote_accounts(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> list[dict]:
    return await svc.get_remote_accounts(connection_id)


@router.post("/simplefin/connections/{connection_id}/sync", response_model=SyncResult)
async def sync_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
    budget_id: uuid.UUID | None = None,
) -> SyncResult:
    if budget_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="budget_id query param is required"
        )
    result = await svc.sync(connection_id, budget_id)
    return SyncResult(**result)


@router.post("/accounts/{account_id}/link-simplefin", status_code=204)
async def link_account(
    account_id: uuid.UUID,
    body: LinkSimpleFINRequest,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> None:
    await account_repo.update(account_id, simplefin_account_id=body.simplefin_account_id)


@router.delete("/accounts/{account_id}/link-simplefin", status_code=204)
async def unlink_account(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> None:
    await account_repo.update(account_id, simplefin_account_id=None)
