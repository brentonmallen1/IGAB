import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from igab.api.v1.schemas.transaction import (
    BulkCategorize,
    BulkClearedUpdate,
    BulkDelete,
    PayeeCreate,
    PayeeMergeRequest,
    PayeeResponse,
    PayeeUpdate,
    PayeeWithCount,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from igab.dependencies import (
    CurrentUser,
    get_payee_repo,
    get_transaction_repo,
    get_transaction_service,
)
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.transaction_service import (
    TransactionCreate as SvcTxnCreate,
)
from igab.services.transaction_service import (
    TransactionService,
)
from igab.services.transaction_service import (
    TransactionUpdate as SvcTxnUpdate,
)

router = APIRouter()


# ─── Transactions ─────────────────────────────────────────────────────────────


@router.get("/accounts/{account_id}/transactions", response_model=list[TransactionResponse])
async def list_account_transactions(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    limit: int = Query(100, le=500),
    offset: int = 0,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[TransactionResponse]:
    txns = await txn_repo.get_for_account(
        account_id,
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
    )
    return [TransactionResponse.model_validate(t) for t in txns]


@router.post(
    "/{budget_id}/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    budget_id: uuid.UUID,
    body: TransactionCreate,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionResponse:
    try:
        if body.splits:
            header = SvcTxnCreate(
                account_id=body.account_id,
                date=body.date,
                amount=body.amount,
                payee_id=body.payee_id,
                payee_name=body.payee_name,
                memo=body.memo,
                cleared=body.cleared,
                approved=body.approved,
            )
            splits = [
                SvcTxnCreate(
                    account_id=body.account_id,
                    date=body.date,
                    amount=s.amount,
                    payee_id=s.payee_id,
                    payee_name=s.payee_name,
                    category_id=s.category_id,
                    memo=s.memo,
                )
                for s in body.splits
            ]
            txn = await txn_service.create_split(budget_id, header, splits)
        else:
            svc_data = SvcTxnCreate(
                account_id=body.account_id,
                date=body.date,
                amount=body.amount,
                payee_id=body.payee_id,
                payee_name=body.payee_name,
                category_id=body.category_id,
                memo=body.memo,
                cleared=body.cleared,
                approved=body.approved,
                transfer_account_id=body.transfer_account_id,
            )
            txn = await txn_service.create(budget_id, svc_data)
    except InvariantViolation as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return TransactionResponse.model_validate(txn)


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: uuid.UUID,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> TransactionResponse:
    try:
        txn = await txn_repo.get_or_raise(transaction_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return TransactionResponse.model_validate(txn)


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: uuid.UUID,
    body: TransactionUpdate,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
    budget_id: uuid.UUID = Query(...),
) -> TransactionResponse:
    try:
        svc_data = SvcTxnUpdate(
            date=body.date,
            amount=body.amount,
            payee_id=body.payee_id,
            category_id=body.category_id,
            memo=body.memo,
            cleared=body.cleared,
            approved=body.approved,
        )
        txn = await txn_service.update(budget_id, transaction_id, svc_data)
    except (NotFoundError, InvariantViolation) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return TransactionResponse.model_validate(txn)


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: uuid.UUID,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
    budget_id: uuid.UUID = Query(...),
) -> None:
    try:
        await txn_service.delete(budget_id, transaction_id)
    except (NotFoundError, InvariantViolation) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.patch("/{budget_id}/transactions/bulk-cleared", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_update_cleared(
    budget_id: uuid.UUID,
    body: BulkClearedUpdate,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> None:
    for txn_id in body.transaction_ids:
        try:
            await txn_service.update(budget_id, txn_id, SvcTxnUpdate(cleared=body.cleared))
        except (NotFoundError, InvariantViolation):
            pass


@router.patch("/{budget_id}/transactions/bulk-categorize", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_categorize(
    budget_id: uuid.UUID,
    body: BulkCategorize,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> None:
    for txn_id in body.transaction_ids:
        try:
            await txn_service.update(budget_id, txn_id, SvcTxnUpdate(category_id=body.category_id))
        except (NotFoundError, InvariantViolation):
            pass


@router.post("/{budget_id}/transactions/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete(
    budget_id: uuid.UUID,
    body: BulkDelete,
    current_user: CurrentUser,
    txn_service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> None:
    for txn_id in body.transaction_ids:
        try:
            await txn_service.delete(budget_id, txn_id)
        except (NotFoundError, InvariantViolation):
            pass


@router.post("/transactions/{transaction_id}/approve", response_model=TransactionResponse)
async def approve_transaction(
    transaction_id: uuid.UUID,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> TransactionResponse:
    txn = await txn_repo.update(transaction_id, approved=True)
    return TransactionResponse.model_validate(txn)


# ─── Payees ───────────────────────────────────────────────────────────────────


@router.get("/{budget_id}/payees", response_model=list[PayeeWithCount])
async def list_payees(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
) -> list[PayeeWithCount]:
    rows = await payee_repo.get_all_with_counts(budget_id)
    return [
        PayeeWithCount(**PayeeResponse.model_validate(p).model_dump(), transaction_count=count)
        for p, count in rows
    ]


@router.post(
    "/{budget_id}/payees",
    response_model=PayeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payee(
    budget_id: uuid.UUID,
    body: PayeeCreate,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
) -> PayeeResponse:
    payee = await payee_repo.find_or_create(budget_id, body.name)
    return PayeeResponse.model_validate(payee)


@router.patch("/payees/{payee_id}", response_model=PayeeResponse)
async def update_payee(
    payee_id: uuid.UUID,
    body: PayeeUpdate,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
) -> PayeeResponse:
    changes = body.model_dump(exclude_none=True)
    payee = await payee_repo.update(payee_id, **changes)
    return PayeeResponse.model_validate(payee)


@router.delete("/payees/{payee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payee(
    payee_id: uuid.UUID,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
) -> None:
    await payee_repo.delete(payee_id)


@router.post("/payees/{payee_id}/merge", status_code=status.HTTP_204_NO_CONTENT)
async def merge_payee(
    payee_id: uuid.UUID,
    body: PayeeMergeRequest,
    current_user: CurrentUser,
    payee_repo: Annotated[PayeeRepository, Depends(get_payee_repo)],
) -> None:
    if payee_id == body.target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge a payee into itself",
        )
    await payee_repo.merge(payee_id, body.target_id)
