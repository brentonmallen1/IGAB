from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from igab.api.v1.schemas.budget_view import (
    BudgetViewCreate,
    BudgetViewResponse,
    BudgetViewUpdate,
)
from igab.dependencies import BudgetAccess, CurrentUser, ViewAccess, get_budget_view_repo
from igab.domain.exceptions import NotFoundError
from igab.repositories.budget_view_repo import BudgetViewRepository

router = APIRouter()


def _conflict(name: str) -> HTTPException:
    """A view name collides with an existing one. Naming a second view the same
    thing is an ordinary mistake, so it gets a 409 the UI can show — not the
    500 an unhandled IntegrityError would produce."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f'A view named "{name}" already exists in this budget',
    )

ViewRepo = Annotated[BudgetViewRepository, Depends(get_budget_view_repo)]


@router.get("/{budget_id}/views", response_model=list[BudgetViewResponse])
async def list_budget_views(
    budget_id: BudgetAccess, current_user: CurrentUser, repo: ViewRepo
) -> list[BudgetViewResponse]:
    return [BudgetViewResponse.model_validate(v) for v in await repo.get_all(budget_id)]


@router.post(
    "/{budget_id}/views",
    response_model=BudgetViewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_budget_view(
    budget_id: BudgetAccess,
    body: BudgetViewCreate,
    current_user: CurrentUser,
    repo: ViewRepo,
) -> BudgetViewResponse:
    try:
        view = await repo.create(
            budget_id=budget_id, name=body.name, hide_unassigned=body.hide_unassigned
        )
        if body.groups:
            await repo.set_groups(view.id, body.groups)
    except IntegrityError as e:
        raise _conflict(body.name) from e
    return BudgetViewResponse.model_validate(await repo.get_full(view.id))


@router.get("/views/{view_id}", response_model=BudgetViewResponse)
async def get_budget_view(
    view_id: ViewAccess, current_user: CurrentUser, repo: ViewRepo
) -> BudgetViewResponse:
    view = await repo.get_full(view_id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    return BudgetViewResponse.model_validate(view)


@router.patch("/views/{view_id}", response_model=BudgetViewResponse)
async def update_budget_view(
    view_id: ViewAccess,
    body: BudgetViewUpdate,
    current_user: CurrentUser,
    repo: ViewRepo,
) -> BudgetViewResponse:
    try:
        changes = {
            k: v
            for k, v in (
                ("name", body.name),
                ("sort_order", body.sort_order),
                ("hide_unassigned", body.hide_unassigned),
            )
            if v is not None
        }
        if changes:
            await repo.update(view_id, **changes)
        # Groups first: placements may reference ids created in the same call.
        if body.groups is not None:
            await repo.set_groups(view_id, body.groups)
        if body.placements is not None:
            await repo.set_placements(view_id, [p.model_dump() for p in body.placements])
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except IntegrityError as e:
        raise _conflict(body.name or "") from e
    return BudgetViewResponse.model_validate(await repo.get_full(view_id))


@router.delete("/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_view(
    view_id: ViewAccess, current_user: CurrentUser, repo: ViewRepo
) -> None:
    try:
        await repo.soft_delete(view_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
