from typing import Annotated

from fastapi import APIRouter, Depends

from igab.api.v1.schemas.reconciliation import (
    ReconcileAdjustmentRequest,
    ReconcileFinishRequest,
    ReconciliationSnapshotResponse,
    ReconciliationStatusResponse,
)
from igab.api.v1.schemas.transaction import TransactionResponse
from igab.dependencies import AccountAccess, CurrentUser, get_reconciliation_service
from igab.services.reconciliation_service import ReconciliationService

router = APIRouter()


@router.get(
    "/accounts/{account_id}/reconcile/status",
    response_model=ReconciliationStatusResponse,
)
async def reconciliation_status(
    account_id: AccountAccess,
    current_user: CurrentUser,
    svc: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
) -> ReconciliationStatusResponse:
    status = await svc.get_status(account_id)
    return ReconciliationStatusResponse(**status)


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
    snapshot = await svc.finish(account_id, body.statement_balance, body.adjustment_transaction_id)
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
    txn = await svc.create_adjustment(account_id, body.adjustment_amount)
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
