"""Wishlist endpoints — thin: parse, authorise, delegate, return."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.wishlist import (
    DeleteWishResponse,
    ProjectCreate,
    ProjectOut,
    ProjectReorder,
    ProjectUpdate,
    WishCreate,
    WishlistResponse,
    WishlistSettingsOut,
    WishlistSettingsUpdate,
    WishOut,
    WishReorder,
    WishUpdate,
)
from igab.dependencies import BudgetAccess, CurrentUser, get_wishlist_service
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.guide.wishlist_service import WishlistService

router = APIRouter()

WishlistDep = Annotated[WishlistService, Depends(get_wishlist_service)]


def _http(e: Exception) -> HTTPException:
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/{budget_id}/wishlist", response_model=WishlistResponse)
async def get_wishlist(
    budget_id: BudgetAccess, current_user: CurrentUser, service: WishlistDep
) -> WishlistResponse:
    return WishlistResponse.model_validate(await service.overview(budget_id))


@router.put("/{budget_id}/wishlist/settings", response_model=WishlistSettingsOut)
async def set_wishlist_settings(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: WishlistDep,
    payload: WishlistSettingsUpdate,
) -> WishlistSettingsOut:
    changes = payload.model_dump(exclude_none=True)
    return WishlistSettingsOut(**await service.set_settings(budget_id, changes))


# ── projects (declared before the wish routes so `projects` never reads as an id) ──


@router.post("/{budget_id}/wishlist/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    budget_id: BudgetAccess, current_user: CurrentUser, service: WishlistDep, payload: ProjectCreate
) -> ProjectOut:
    try:
        return ProjectOut.model_validate(
            await service.create_project(budget_id, payload.model_dump())
        )
    except (InvariantViolation, NotFoundError) as e:
        raise _http(e) from e


@router.post("/{budget_id}/wishlist/projects/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_projects(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: WishlistDep,
    payload: ProjectReorder,
) -> None:
    try:
        await service.reorder_projects(budget_id, payload.project_ids)
    except InvariantViolation as e:
        raise _http(e) from e


@router.patch("/{budget_id}/wishlist/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    budget_id: BudgetAccess,
    project_id: uuid.UUID,
    current_user: CurrentUser,
    service: WishlistDep,
    payload: ProjectUpdate,
) -> ProjectOut:
    try:
        return ProjectOut.model_validate(
            await service.update_project(
                budget_id, project_id, payload.model_dump(exclude_unset=True)
            )
        )
    except (InvariantViolation, NotFoundError) as e:
        raise _http(e) from e


@router.delete(
    "/{budget_id}/wishlist/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_project(
    budget_id: BudgetAccess, project_id: uuid.UUID, current_user: CurrentUser, service: WishlistDep
) -> None:
    try:
        await service.delete_project(budget_id, project_id)
    except (InvariantViolation, NotFoundError) as e:
        raise _http(e) from e


# ── wishes ──


@router.post("/{budget_id}/wishlist", response_model=WishOut, status_code=201)
async def create_wish(
    budget_id: BudgetAccess, current_user: CurrentUser, service: WishlistDep, payload: WishCreate
) -> WishOut:
    try:
        return WishOut.model_validate(await service.create(budget_id, payload.model_dump()))
    except (InvariantViolation, NotFoundError) as e:
        raise _http(e) from e


@router.post("/{budget_id}/wishlist/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_wishes(
    budget_id: BudgetAccess, current_user: CurrentUser, service: WishlistDep, payload: WishReorder
) -> None:
    try:
        await service.reorder_items(budget_id, payload.item_ids)
    except InvariantViolation as e:
        raise _http(e) from e


@router.patch("/{budget_id}/wishlist/{item_id}", response_model=WishOut)
async def update_wish(
    budget_id: BudgetAccess,
    item_id: uuid.UUID,
    current_user: CurrentUser,
    service: WishlistDep,
    payload: WishUpdate,
) -> WishOut:
    try:
        return WishOut.model_validate(
            await service.update(budget_id, item_id, payload.model_dump(exclude_unset=True))
        )
    except (InvariantViolation, NotFoundError) as e:
        raise _http(e) from e


@router.delete("/{budget_id}/wishlist/{item_id}", response_model=DeleteWishResponse)
async def delete_wish(
    budget_id: BudgetAccess, item_id: uuid.UUID, current_user: CurrentUser, service: WishlistDep
) -> DeleteWishResponse:
    try:
        return DeleteWishResponse.model_validate(await service.delete(budget_id, item_id))
    except (InvariantViolation, NotFoundError) as e:
        raise _http(e) from e


@router.post("/{budget_id}/wishlist/{item_id}/affirm", status_code=status.HTTP_204_NO_CONTENT)
async def affirm_wish(
    budget_id: BudgetAccess, item_id: uuid.UUID, current_user: CurrentUser, service: WishlistDep
) -> None:
    try:
        await service.affirm(budget_id, item_id)
    except (InvariantViolation, NotFoundError) as e:
        raise _http(e) from e
