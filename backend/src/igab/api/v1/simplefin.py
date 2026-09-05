import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.simplefin import (
    AccountSyncStatusResponse,
    LinkSimpleFINRequest,
    RateLimitStatus,
    SimpleFINConfigResponse,
    SimpleFINConnectionResponse,
    SimpleFINSetupRequest,
    SimpleFINUpdateRequest,
    SyncAllResult,
    SyncResult,
    TransactionMatchResponse,
)
from igab.dependencies import (
    AccountAccess,
    BudgetAccess,
    ConnectionAccess,
    CurrentUser,
    MatchAccess,
    get_account_repo,
    get_change_recorder,
    get_simplefin_service,
    get_transaction_matching_service,
)
from igab.integrations.simplefin.encryption import (
    GENERATE_KEY_COMMAND,
    SimpleFINNotConfigured,
    key_problem,
)
from igab.repositories.account_repo import AccountRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match
from igab.services.simplefin_service import SimpleFINService
from igab.services.transaction_matching_service import TransactionMatchingService

logger = logging.getLogger(__name__)

router = APIRouter(route_class=CommitRoute)

_CREATE_URL = "https://beta-bridge.simplefin.org/simplefin/create"


def _setup_error_message(exc: Exception) -> str:
    name = type(exc).__name__
    msg = str(exc)

    if isinstance(exc, SimpleFINNotConfigured):
        # Never blame the token for this: setup() checks the key *before* the
        # exchange, so the token the user pasted is still unused.
        return (
            f"{msg} Your setup token was not used — it will still work once the key is "
            f"set. Generate one with: {GENERATE_KEY_COMMAND}"
        )
    # Only the token's own decode failure, matched on the message the client
    # raises. A blanket `isinstance(exc, ValueError)` used to land here, which
    # is how a missing encryption key was reported as an invalid token — and
    # sent people back to burn a fresh token on every retry.
    if "base64" in msg.lower() or "decode" in msg.lower():
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


@router.get("/simplefin/config", response_model=SimpleFINConfigResponse)
async def get_simplefin_config(current_user: CurrentUser) -> SimpleFINConfigResponse:
    """Whether bank sync can run on this server, and what to do if it cannot.

    The UI asks before showing the setup form, so a server without an
    encryption key says so up front instead of after the user has spent a
    single-use SimpleFIN token on it.
    """
    problem = key_problem()
    return SimpleFINConfigResponse(
        configured=problem is None,
        problem=problem,
        generate_key_command=GENERATE_KEY_COMMAND,
    )


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
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
                if isinstance(e, SimpleFINNotConfigured)
                else status.HTTP_400_BAD_REQUEST
            ),
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
    connection_id: ConnectionAccess,
    body: SimpleFINUpdateRequest,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> SimpleFINConnectionResponse:
    updates = body.model_dump(exclude_none=True)
    conn = await svc.update_connection(connection_id, **updates)
    return SimpleFINConnectionResponse.model_validate(conn)


@router.delete("/simplefin/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: ConnectionAccess,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> None:
    await svc.delete(connection_id)


@router.get("/simplefin/connections/{connection_id}/status", response_model=RateLimitStatus)
async def get_connection_status(
    connection_id: ConnectionAccess,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> RateLimitStatus:
    conn = await svc.repo.get(connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return RateLimitStatus(**svc.get_rate_limit_status(conn))


@router.get("/simplefin/connections/{connection_id}/accounts")
async def get_remote_accounts(
    connection_id: ConnectionAccess,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> list[dict]:
    return await svc.get_remote_accounts(connection_id)


@router.post("/simplefin/connections/{connection_id}/sync", response_model=SyncResult)
async def sync_connection(
    connection_id: ConnectionAccess,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
    budget_id: BudgetAccess,
    account_simplefin_id: str | None = None,
) -> SyncResult:
    sync_type = "account" if account_simplefin_id else "global"
    result = await svc.sync(
        connection_id,
        budget_id,
        sync_type=sync_type,
        account_simplefin_id=account_simplefin_id,
    )
    return SyncResult(**result)


@router.post("/{budget_id}/simplefin/sync-all", response_model=SyncAllResult)
async def sync_all_connections(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> SyncAllResult:
    """Sync every connection this user has, in one go.

    The Accounts page's "Sync All" only ever reached `connections[0]`, so a
    second bank was never synced by it. This is the one implementation the
    page, the sidebar and the command palette all call.
    """
    result = await svc.sync_all(current_user.id, budget_id)
    return SyncAllResult(**result)


async def _recorded_account_update(
    recorder: ChangeRecorder, account_repo: AccountRepository, account_id, **updates
) -> None:
    """The one spelling of "change account fields and record it" for the
    bank-link endpoints — linking is a user decision, so it undoes."""
    account = await account_repo.get_or_raise(account_id)
    before = snapshot("account", account)
    updated = await account_repo.update(account_id, **updates)
    after = snapshot("account", updated)
    if snapshots_match(after, before):  # non-empty diff — something changed
        await recorder.record(
            budget_id=updated.budget_id,
            entity_type="account",
            entity_id=updated.id,
            action="update",
            before=before,
            after=after,
        )


@router.post("/accounts/{account_id}/link-simplefin", status_code=204)
async def link_account(
    account_id: AccountAccess,
    body: LinkSimpleFINRequest,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> None:
    await _recorded_account_update(
        recorder,
        account_repo,
        account_id,
        simplefin_account_id=body.simplefin_account_id,
        simplefin_account_name=body.simplefin_account_name,
    )


@router.delete("/accounts/{account_id}/link-simplefin", status_code=204)
async def unlink_account(
    account_id: AccountAccess,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
) -> None:
    await _recorded_account_update(
        recorder, account_repo, account_id, simplefin_account_id=None, simplefin_account_name=None
    )


@router.get("/accounts/{account_id}/sync-status", response_model=AccountSyncStatusResponse)
async def get_account_sync_status(
    account_id: AccountAccess,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> AccountSyncStatusResponse:
    account = await account_repo.get_or_raise(account_id)
    return AccountSyncStatusResponse.model_validate(account)


@router.patch("/accounts/{account_id}/simplefin-settings", status_code=204)
async def update_account_simplefin_settings(
    account_id: AccountAccess,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    recorder: Annotated[ChangeRecorder, Depends(get_change_recorder)],
    simplefin_sync_enabled: bool | None = None,
) -> None:
    updates: dict = {}
    if simplefin_sync_enabled is not None:
        updates["simplefin_sync_enabled"] = simplefin_sync_enabled
    if updates:
        await _recorded_account_update(recorder, account_repo, account_id, **updates)


# ── Transaction match review ─────────────────────────────────────────────────


@router.get(
    "/simplefin/matches",
    response_model=list[TransactionMatchResponse],
)
async def list_pending_matches(
    current_user: CurrentUser,
    matching_svc: Annotated[TransactionMatchingService, Depends(get_transaction_matching_service)],
    budget_id: BudgetAccess,
) -> list[TransactionMatchResponse]:
    matches = await matching_svc.match_repo.get_pending_for_budget(budget_id)
    return [TransactionMatchResponse.model_validate(m) for m in matches]


@router.get(
    "/accounts/{account_id}/pending-matches",
    response_model=list[TransactionMatchResponse],
)
async def list_pending_matches_for_account(
    account_id: AccountAccess,
    current_user: CurrentUser,
    matching_svc: Annotated[TransactionMatchingService, Depends(get_transaction_matching_service)],
) -> list[TransactionMatchResponse]:
    matches = await matching_svc.match_repo.get_pending_for_account(account_id)
    return [TransactionMatchResponse.model_validate(m) for m in matches]


@router.post("/simplefin/matches/{match_id}/accept", status_code=204)
async def accept_match(
    match_id: MatchAccess,
    current_user: CurrentUser,
    matching_svc: Annotated[TransactionMatchingService, Depends(get_transaction_matching_service)],
) -> None:
    from igab.domain.exceptions import InvariantViolation

    try:
        await matching_svc.accept_match(match_id)
    except InvariantViolation as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/simplefin/matches/{match_id}/reject", status_code=204)
async def reject_match(
    match_id: MatchAccess,
    current_user: CurrentUser,
    matching_svc: Annotated[TransactionMatchingService, Depends(get_transaction_matching_service)],
) -> None:
    await matching_svc.reject_match(match_id)
