import logging
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.simplefin import (
    AccountSyncStatusResponse,
    LinkSimpleFINRequest,
    RateLimitStatus,
    SimpleFINConnectionResponse,
    SimpleFINSetupRequest,
    SimpleFINUpdateRequest,
    SyncResult,
    TransactionMatchResponse,
)
from igab.dependencies import (
    CurrentUser,
    get_account_repo,
    get_simplefin_service,
    get_transaction_matching_service,
)
from igab.repositories.account_repo import AccountRepository
from igab.services.simplefin_service import SimpleFINService
from igab.services.transaction_matching_service import TransactionMatchingService

logger = logging.getLogger(__name__)

router = APIRouter()

_CREATE_URL = "https://beta-bridge.simplefin.org/simplefin/create"


def _setup_error_message(exc: Exception) -> str:
    name = type(exc).__name__
    msg = str(exc)

    if "base64" in msg.lower() or "decode" in msg.lower() or isinstance(exc, ValueError):
        return (
            "Invalid setup token — make sure you copied the full token from "
            f"{_CREATE_URL} and haven't used it before."
        )
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403, 404, 410):
            return (
                f"SimpleFIN rejected the token (HTTP {code}). "
                "Tokens are single-use and expire quickly — generate a new one at "
                f"{_CREATE_URL} and connect within a minute or two."
            )
        if code >= 500:
            return f"SimpleFIN returned a server error (HTTP {code}). Try again in a moment."
        return f"SimpleFIN rejected the request (HTTP {code}): {exc.response.text[:120]}"
    if isinstance(exc, httpx.TimeoutException):
        return "Timed out contacting SimpleFIN. Check your network and try again."
    if isinstance(exc, httpx.ConnectError):
        return "Could not reach SimpleFIN. Check your internet connection and try again."
    # Fallback — still more useful than a raw traceback
    return f"Setup failed ({name}): {msg}"


@router.post("/simplefin/setup", response_model=SimpleFINConnectionResponse, status_code=201)
async def setup_simplefin(
    body: SimpleFINSetupRequest,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> SimpleFINConnectionResponse:
    try:
        conn = await svc.setup(current_user.id, body.setup_token)
    except Exception as e:
        logger.exception("SimpleFIN setup failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_setup_error_message(e),
        ) from e
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
    updates = body.model_dump(exclude_none=True)
    conn = await svc.update_connection(connection_id, **updates)
    return SimpleFINConnectionResponse.model_validate(conn)


@router.delete("/simplefin/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> None:
    await svc.delete(connection_id)


@router.get("/simplefin/connections/{connection_id}/status", response_model=RateLimitStatus)
async def get_connection_status(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> RateLimitStatus:
    conn = await svc.repo.get(connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return RateLimitStatus(**svc.get_rate_limit_status(conn))


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
    account_simplefin_id: str | None = None,
) -> SyncResult:
    if budget_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="budget_id query param is required"
        )
    sync_type = "account" if account_simplefin_id else "global"
    result = await svc.sync(
        connection_id,
        budget_id,
        sync_type=sync_type,
        account_simplefin_id=account_simplefin_id,
    )
    return SyncResult(**result)


@router.post("/accounts/{account_id}/link-simplefin", status_code=204)
async def link_account(
    account_id: uuid.UUID,
    body: LinkSimpleFINRequest,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> None:
    await account_repo.update(
        account_id,
        simplefin_account_id=body.simplefin_account_id,
        simplefin_account_name=body.simplefin_account_name,
    )


@router.delete("/accounts/{account_id}/link-simplefin", status_code=204)
async def unlink_account(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> None:
    await account_repo.update(account_id, simplefin_account_id=None, simplefin_account_name=None)


@router.get("/accounts/{account_id}/sync-status", response_model=AccountSyncStatusResponse)
async def get_account_sync_status(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> AccountSyncStatusResponse:
    account = await account_repo.get_or_raise(account_id)
    return AccountSyncStatusResponse.model_validate(account)


@router.patch("/accounts/{account_id}/simplefin-settings", status_code=204)
async def update_account_simplefin_settings(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    simplefin_sync_enabled: bool | None = None,
) -> None:
    updates: dict = {}
    if simplefin_sync_enabled is not None:
        updates["simplefin_sync_enabled"] = simplefin_sync_enabled
    if updates:
        await account_repo.update(account_id, **updates)


# ── Transaction match review ─────────────────────────────────────────────────


@router.get(
    "/simplefin/matches",
    response_model=list[TransactionMatchResponse],
)
async def list_pending_matches(
    current_user: CurrentUser,
    matching_svc: Annotated[TransactionMatchingService, Depends(get_transaction_matching_service)],
    budget_id: uuid.UUID | None = None,
) -> list[TransactionMatchResponse]:
    if budget_id is None:
        raise HTTPException(status_code=400, detail="budget_id query param is required")
    matches = await matching_svc.match_repo.get_pending_for_budget(budget_id)
    return [TransactionMatchResponse.model_validate(m) for m in matches]


@router.post("/simplefin/matches/{match_id}/accept", status_code=204)
async def accept_match(
    match_id: uuid.UUID,
    current_user: CurrentUser,
    matching_svc: Annotated[TransactionMatchingService, Depends(get_transaction_matching_service)],
) -> None:
    await matching_svc.accept_match(match_id)


@router.post("/simplefin/matches/{match_id}/reject", status_code=204)
async def reject_match(
    match_id: uuid.UUID,
    current_user: CurrentUser,
    matching_svc: Annotated[TransactionMatchingService, Depends(get_transaction_matching_service)],
) -> None:
    await matching_svc.reject_match(match_id)
