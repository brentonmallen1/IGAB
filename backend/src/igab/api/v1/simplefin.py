import logging
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.simplefin import (
    AccountSyncStatusResponse,
    LinkSimpleFINRequest,
    RateLimitStatus,
    RefetchRequest,
    SimpleFINConfigResponse,
    SimpleFINConnectionResponse,
    SimpleFINSetupRequest,
    SimpleFINUpdateRequest,
    SyncAllResult,
    SyncHealthResponse,
    SyncResult,
    SyncRunDetailResponse,
    SyncRunListResponse,
    SyncRunResponse,
    SyncRunUndoResult,
    TransactionMatchResponse,
    UnservedAccount,
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
    get_sync_run_repo,
    get_transaction_matching_service,
    get_undo_service,
)
from igab.domain.bank_balance import as_of_date, drift_is_a_fault, explain_drift
from igab.domain.exceptions import NotFoundError
from igab.integrations.simplefin.encryption import (
    GENERATE_KEY_COMMAND,
    SimpleFINNotConfigured,
    key_problem,
)
from igab.repositories.account_repo import AccountRepository
from igab.repositories.sync_run_repo import SyncRunRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match
from igab.services.simplefin_service import SimpleFINService
from igab.services.transaction_matching_service import TransactionMatchingService
from igab.services.undo_service import BatchUndo, UndoService

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


# Connection lifecycle is deliberately absent from the change log (see
# change_log.py's exclusion list): connections are user-scoped credentials
# with no budget to file under. The budget-visible effects of a sync — the
# transactions — record through TransactionService as source="system".
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
    # A relink also forgets when the account last synced, so the next run
    # asks the bank for the full window rather than the days since the run
    # that served nothing. The first relink after the bridge re-issued an
    # account id was followed by a sync anchored to the broken run's own
    # stamp, and the days the broken link had missed were never requested.
    await _recorded_account_update(
        recorder,
        account_repo,
        account_id,
        simplefin_account_id=body.simplefin_account_id,
        simplefin_account_name=body.simplefin_account_name,
        last_simplefin_sync_at=None,
    )


@router.post("/accounts/{account_id}/simplefin-refetch", response_model=SyncResult)
async def refetch_account(
    account_id: AccountAccess,
    body: RefetchRequest,
    current_user: CurrentUser,
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
    svc: Annotated[SimpleFINService, Depends(get_simplefin_service)],
) -> SyncResult:
    """Ask the bank for the full window again, for this account only.

    The recovery after a gap: forget when the account last synced and run an
    account-scoped sync, so the request reaches back the bridge's whole
    90 days. Safe to press at any time — rows the register already holds
    re-stamp or skip, and only what is missing imports — which is what makes
    it a button rather than a support procedure.
    """
    account = await account_repo.get_or_raise(account_id)
    if not account.simplefin_account_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is not linked")
    conn = await svc.repo.get(body.connection_id)
    if conn is None or conn.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    await account_repo.update(account_id, last_simplefin_sync_at=None)
    result = await svc.sync(
        body.connection_id,
        account.budget_id,
        sync_type="account",
        account_simplefin_id=account.simplefin_account_id,
    )
    return SyncResult(**result)


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


# ─── Sync log ─────────────────────────────────────────────────────────────────
#
# Literal sub-paths are declared BEFORE the `{run_id}` route: FastAPI matches
# in declaration order, so "/sync-runs/health" would otherwise be parsed as a
# run id and 422 on the UUID. Same trap as the note in ai_chat.py.


@router.get("/{budget_id}/simplefin/sync-runs/health", response_model=SyncHealthResponse)
async def get_sync_health(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    runs: Annotated[SyncRunRepository, Depends(get_sync_run_repo)],
    account_repo: Annotated[AccountRepository, Depends(get_account_repo)],
) -> SyncHealthResponse:
    """Whether anything about bank sync needs attention right now.

    This is what badges the nav. It reads the most recent run only: a finding
    from three runs ago would claim a link is broken after it was fixed, and
    an app that cries wolf is one whose badges get ignored — which is the
    failure mode this whole feature exists to correct.
    """
    latest = await runs.latest_with_orphans(budget_id)
    if latest is None:
        return SyncHealthResponse()
    detail = await runs.get(latest.id)
    accounts = detail.accounts if detail is not None else []

    # Drift is re-judged against the ledger as it stands now. The run said
    # "off by X"; the person then deleted the duplicates; the badge must not
    # go on saying X until the next hourly run happens to agree.
    still_off: list[dict] = []
    for entry in latest.balance_drift:
        try:
            account = await account_repo.get_or_raise(uuid.UUID(str(entry.get("account_id"))))
        except (NotFoundError, ValueError):
            continue
        cleared = await account_repo.get_cleared_balance(account.id)
        drift = explain_drift(
            account.simplefin_balance,
            cleared,
            unposted_cleared=await account_repo.get_unposted_cleared(account.id),
            balance_as_of=as_of_date(account.simplefin_balance_date),
            newest_cleared_on=await account_repo.get_newest_cleared_on(account.id),
        )
        if drift is not None and drift_is_a_fault(
            drift, reconciled=account.last_reconciled_at is not None
        ):
            still_off.append(
                {
                    **entry,
                    "bank_balance": str(drift.reported),
                    "ledger_cleared_balance": str(drift.ledger_cleared),
                    "unexplained_amount": str(drift.unexplained),
                    "unposted_cleared": str(drift.unposted_cleared),
                }
            )

    return SyncHealthResponse(
        orphaned_links=latest.orphaned_links,
        needs_auth=[e for e in latest.bank_errors if e.get("code") == "con.auth"],
        balance_drift=still_off,
        # Not re-judged like drift above: a refusal is a statement about
        # what the run declined to write, and nothing the user does to the
        # register afterwards makes it untrue. It clears on the next sync.
        refused_anchors=list(latest.refused_anchors or []),
        unserved=[
            UnservedAccount(account_id=a.account_id, account_name=a.account_name)
            for a in accounts
            if a.account_id is not None
            and (a.orphaned or (a.feed_txn_count == 0 and a.bank_balance is None))
        ],
        last_run_at=latest.created_at,
    )


@router.post("/{budget_id}/simplefin/sync-runs/{run_id}/undo", response_model=SyncRunUndoResult)
async def undo_sync_run(
    budget_id: BudgetAccess,
    run_id: uuid.UUID,
    current_user: CurrentUser,
    runs: Annotated[SyncRunRepository, Depends(get_sync_run_repo)],
    undo: Annotated[UndoService, Depends(get_undo_service)],
) -> SyncRunUndoResult:
    """Take back what one run wrote — the imports, the adoptions, the rows
    it removed, the relink — as one unit. Rows the person has edited since
    are left alone and counted as skipped.

    This is the recovery a bad run needs and never had: ⌘Z skips sync
    changes by design, and "revert everything after a point" also reverts
    the person's own work since.
    """
    run = await runs.get(run_id)
    if run is None or run.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync run not found")
    if run.change_batch_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This run predates per-run undo and cannot be taken back as a unit",
        )
    if run.undone_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already undone")
    try:
        result = await undo.undo_batch_leniently(budget_id, run.change_batch_id)
    except NotFoundError:
        # Nothing was recorded — a run that imported nothing has nothing to
        # take back, and saying so is the honest outcome.
        result = BatchUndo([], [])
    await runs.mark_undone(run)
    return SyncRunUndoResult(undone=len(result.undone), skipped=len(result.skipped))


@router.get("/{budget_id}/simplefin/sync-runs", response_model=SyncRunListResponse)
async def list_sync_runs(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    runs: Annotated[SyncRunRepository, Depends(get_sync_run_repo)],
    limit: int = 50,
    offset: int = 0,
) -> SyncRunListResponse:
    rows, total = await runs.list_runs(budget_id=budget_id, limit=min(limit, 200), offset=offset)
    return SyncRunListResponse(
        runs=[SyncRunResponse.model_validate(r) for r in rows], total_count=total
    )


@router.get("/{budget_id}/simplefin/sync-runs/{run_id}", response_model=SyncRunDetailResponse)
async def get_sync_run(
    budget_id: BudgetAccess,
    run_id: uuid.UUID,
    current_user: CurrentUser,
    runs: Annotated[SyncRunRepository, Depends(get_sync_run_repo)],
) -> SyncRunDetailResponse:
    run = await runs.get(run_id)
    if run is None or run.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync run not found")
    return SyncRunDetailResponse.model_validate(run)
