from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.reconciliation import (
    ReconcileAdjustmentRequest,
    ReconcileFinishRequest,
    ReconciliationSnapshotResponse,
    ReconciliationStatusResponse,
)
from igab.api.v1.schemas.transaction import TransactionResponse
from igab.dependencies import AccountAccess, CurrentUser, get_reconciliation_service
from igab.services.reconciliation_service import ReconciliationBlocked, ReconciliationService

router = APIRouter(route_class=CommitRoute)


@router.get(
    "/accounts/{account_id}/reconcile/status",
    response_model=ReconciliationStatusResponse,
)
async def reconciliation_status(
    account_id: AccountAccess,
    current_user: CurrentUser,
    svc: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
) -> ReconciliationStatusResponse:
    return ReconciliationStatusResponse(**await svc.get_status(account_id))


@router.post(
    "/accounts/{account_id}/reconcile/finish",
    response_model=ReconciliationSnapshotResponse,
)
async def finish_reconciliation(
    account_id: AccountAccess,
    body: ReconcileFinishRequest,
    current_user: CurrentUser,
    svc: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
) -> ReconciliationSnapshotResponse:
    try:
        snapshot = await svc.finish(
            account_id, body.statement_balance, body.adjustment_transaction_id
        )
    except ReconciliationBlocked as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return ReconciliationSnapshotResponse.model_validate(snapshot)


@router.post(
    "/accounts/{account_id}/reconcile/adjustment",
    response_model=TransactionResponse,
)
async def create_reconcile_adjustment(
    account_id: AccountAccess,
    body: ReconcileAdjustmentRequest,
    current_user: CurrentUser,
    svc: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
) -> TransactionResponse:
    try:
        txn = await svc.create_adjustment(account_id, body.adjustment_amount)
    except ReconciliationBlocked as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return TransactionResponse.model_validate(txn)


@router.get(
    "/accounts/{account_id}/reconcile/history",
    response_model=list[ReconciliationSnapshotResponse],
)
async def reconciliation_history(
    account_id: AccountAccess,
    current_user: CurrentUser,
    svc: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
) -> list[ReconciliationSnapshotResponse]:
    snaps = await svc.get_history(account_id)
    return [ReconciliationSnapshotResponse.model_validate(s) for s in snaps]
