"""Category planner endpoints — thin: parse, authorise, delegate, return.

Plans are whole-document: the client always holds the full payload (it is
rendering it) and autosaves it with PUT, so there are no per-row routes.
Rename is a separate PATCH so a rename cannot race an in-flight autosave and
resurrect a stale payload. Concurrent editors are last-write-wins —
scratchpad semantics, on purpose.

Apply-targets is the one action that touches the real budget; its preview
returns the same classification apply executes (one implementation, in the
service), so the confirmation sheet cannot disagree with what happens.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.category_plan import (
    ApplyPreviewOut,
    ApplyResultOut,
    PlanCreate,
    PlanDuplicate,
    PlanOut,
    PlanPut,
    PlanRename,
    PlanSummaryOut,
)
from igab.dependencies import BudgetAccess, CurrentUser, get_category_plan_service
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.services.category_plan_service import CategoryPlanService

router = APIRouter(route_class=CommitRoute)

PlanServiceDep = Annotated[CategoryPlanService, Depends(get_category_plan_service)]


def _http(e: Exception) -> HTTPException:
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/{budget_id}/category-plans", response_model=list[PlanSummaryOut])
async def list_plans(
    budget_id: BudgetAccess, current_user: CurrentUser, service: PlanServiceDep
) -> list[PlanSummaryOut]:
    return [PlanSummaryOut.model_validate(p) for p in await service.list_plans(budget_id)]


@router.post("/{budget_id}/category-plans", response_model=PlanOut, status_code=201)
async def create_plan(
    budget_id: BudgetAccess, current_user: CurrentUser, service: PlanServiceDep, body: PlanCreate
) -> PlanOut:
    payload = body.payload.model_dump(mode="json") if body.payload is not None else None
    try:
        return PlanOut.model_validate(await service.create(budget_id, body.name, payload))
    except InvariantViolation as e:
        raise _http(e) from e


@router.get("/{budget_id}/category-plans/{plan_id}", response_model=PlanOut)
async def get_plan(
    budget_id: BudgetAccess,
    plan_id: uuid.UUID,
    current_user: CurrentUser,
    service: PlanServiceDep,
) -> PlanOut:
    try:
        return PlanOut.model_validate(await service.get(budget_id, plan_id))
    except NotFoundError as e:
        raise _http(e) from e


@router.put("/{budget_id}/category-plans/{plan_id}", response_model=PlanOut)
async def save_plan(
    budget_id: BudgetAccess,
    plan_id: uuid.UUID,
    current_user: CurrentUser,
    service: PlanServiceDep,
    body: PlanPut,
) -> PlanOut:
    try:
        return PlanOut.model_validate(
            await service.update_payload(budget_id, plan_id, body.payload.model_dump(mode="json"))
        )
    except NotFoundError as e:
        raise _http(e) from e


@router.patch("/{budget_id}/category-plans/{plan_id}", response_model=PlanOut)
async def rename_plan(
    budget_id: BudgetAccess,
    plan_id: uuid.UUID,
    current_user: CurrentUser,
    service: PlanServiceDep,
    body: PlanRename,
) -> PlanOut:
    try:
        return PlanOut.model_validate(await service.rename(budget_id, plan_id, body.name))
    except (InvariantViolation, NotFoundError) as e:
        raise _http(e) from e


@router.post(
    "/{budget_id}/category-plans/{plan_id}/duplicate", response_model=PlanOut, status_code=201
)
async def duplicate_plan(
    budget_id: BudgetAccess,
    plan_id: uuid.UUID,
    current_user: CurrentUser,
    service: PlanServiceDep,
    body: PlanDuplicate,
) -> PlanOut:
    try:
        return PlanOut.model_validate(await service.duplicate(budget_id, plan_id, body.name))
    except (InvariantViolation, NotFoundError) as e:
        raise _http(e) from e


@router.delete("/{budget_id}/category-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    budget_id: BudgetAccess,
    plan_id: uuid.UUID,
    current_user: CurrentUser,
    service: PlanServiceDep,
) -> None:
    try:
        await service.delete(budget_id, plan_id)
    except NotFoundError as e:
        raise _http(e) from e


@router.post(
    "/{budget_id}/category-plans/{plan_id}/apply-targets/preview",
    response_model=ApplyPreviewOut,
)
async def preview_apply_targets(
    budget_id: BudgetAccess,
    plan_id: uuid.UUID,
    current_user: CurrentUser,
    service: PlanServiceDep,
) -> ApplyPreviewOut:
    try:
        return ApplyPreviewOut.model_validate(await service.preview_apply(budget_id, plan_id))
    except NotFoundError as e:
        raise _http(e) from e


@router.post("/{budget_id}/category-plans/{plan_id}/apply-targets", response_model=ApplyResultOut)
async def apply_targets(
    budget_id: BudgetAccess,
    plan_id: uuid.UUID,
    current_user: CurrentUser,
    service: PlanServiceDep,
) -> ApplyResultOut:
    try:
        return ApplyResultOut.model_validate(await service.apply(budget_id, plan_id))
    except NotFoundError as e:
        raise _http(e) from e
