import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.scheduled_transaction import (
    ScheduledTransactionCreate,
    ScheduledTransactionResponse,
    ScheduledTransactionUpdate,
)
from igab.dependencies import CurrentUser, get_scheduled_transaction_service
from igab.services.scheduled_transaction_service import (
    ScheduledTransactionCreate as ServiceCreate,
    ScheduledTransactionService,
)

router = APIRouter()


@router.get(
    "/{budget_id}/scheduled-transactions",
    response_model=list[ScheduledTransactionResponse],
)
async def list_scheduled_transactions(
    budget_id: uuid.UUID,
    current_user: CurrentUser,
    svc: Annotated[ScheduledTransactionService, Depends(get_scheduled_transaction_service)],
) -> list[ScheduledTransactionResponse]:
    items = await svc.list(budget_id)
    return [ScheduledTransactionResponse.model_validate(i) for i in items]


@router.post(
    "/{budget_id}/scheduled-transactions",
    response_model=ScheduledTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scheduled_transaction(
    budget_id: uuid.UUID,
    body: ScheduledTransactionCreate,
    current_user: CurrentUser,
    svc: Annotated[ScheduledTransactionService, Depends(get_scheduled_transaction_service)],
) -> ScheduledTransactionResponse:
    data = ServiceCreate(
        account_id=body.account_id,
        amount=body.amount,
        frequency=body.frequency,
        start_date=body.start_date,
        payee_id=body.payee_id,
        category_id=body.category_id,
        memo=body.memo,
        end_date=body.end_date,
        auto_create=body.auto_create,
        days_before_reminder=body.days_before_reminder,
    )
    item = await svc.create(budget_id, data)
    return ScheduledTransactionResponse.model_validate(item)


@router.patch(
    "/scheduled-transactions/{id}",
    response_model=ScheduledTransactionResponse,
)
async def update_scheduled_transaction(
    id: uuid.UUID,
    body: ScheduledTransactionUpdate,
    current_user: CurrentUser,
    svc: Annotated[ScheduledTransactionService, Depends(get_scheduled_transaction_service)],
) -> ScheduledTransactionResponse:
    changes = body.model_dump(exclude_none=True)
    item = await svc.update(id, **changes)
    return ScheduledTransactionResponse.model_validate(item)


@router.delete("/scheduled-transactions/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scheduled_transaction(
    id: uuid.UUID,
    current_user: CurrentUser,
    svc: Annotated[ScheduledTransactionService, Depends(get_scheduled_transaction_service)],
) -> None:
    await svc.delete(id)


@router.post(
    "/scheduled-transactions/{id}/skip",
    response_model=ScheduledTransactionResponse,
)
async def skip_scheduled_transaction(
    id: uuid.UUID,
    current_user: CurrentUser,
    svc: Annotated[ScheduledTransactionService, Depends(get_scheduled_transaction_service)],
) -> ScheduledTransactionResponse:
    item = await svc.skip(id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ScheduledTransactionResponse.model_validate(item)


@router.post("/scheduled-transactions/{id}/enter", status_code=status.HTTP_204_NO_CONTENT)
async def enter_scheduled_transaction(
    id: uuid.UUID,
    current_user: CurrentUser,
    svc: Annotated[ScheduledTransactionService, Depends(get_scheduled_transaction_service)],
    budget_id: uuid.UUID | None = None,
) -> None:
    if budget_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="budget_id query param required"
        )
    await svc.enter_now(id, budget_id)
