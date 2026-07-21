from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.budget_view import BudgetViewCreate, BudgetViewResponse, BudgetViewUpdate
from igab.dependencies import BudgetAccess, CurrentUser, ViewAccess, get_budget_view_repo
from igab.domain.exceptions import NotFoundError
from igab.repositories.budget_view_repo import BudgetViewRepository

router = APIRouter()


@router.get("/{budget_id}/views", response_model=list[BudgetViewResponse])
async def list_budget_views(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    view_repo: Annotated[BudgetViewRepository, Depends(get_budget_view_repo)],
) -> list[BudgetViewResponse]:
    views = await view_repo.get_all(budget_id)
    return [BudgetViewResponse.model_validate(v) for v in views]


@router.post(
    "/{budget_id}/views",
    response_model=BudgetViewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_budget_view(
    budget_id: BudgetAccess,
    body: BudgetViewCreate,
    current_user: CurrentUser,
    view_repo: Annotated[BudgetViewRepository, Depends(get_budget_view_repo)],
) -> BudgetViewResponse:
    view = await view_repo.create(budget_id=budget_id, name=body.name)
    await view_repo.set_categories(view.id, body.category_ids)
    view = await view_repo.get_with_categories(view.id)
    return BudgetViewResponse.model_validate(view)


@router.get("/views/{view_id}", response_model=BudgetViewResponse)
async def get_budget_view(
    view_id: ViewAccess,
    current_user: CurrentUser,
    view_repo: Annotated[BudgetViewRepository, Depends(get_budget_view_repo)],
) -> BudgetViewResponse:
    view = await view_repo.get_with_categories(view_id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    return BudgetViewResponse.model_validate(view)


@router.patch("/views/{view_id}", response_model=BudgetViewResponse)
async def update_budget_view(
    view_id: ViewAccess,
    body: BudgetViewUpdate,
    current_user: CurrentUser,
    view_repo: Annotated[BudgetViewRepository, Depends(get_budget_view_repo)],
) -> BudgetViewResponse:
    try:
        changes = body.model_dump(exclude_none=True)
        category_ids = changes.pop("category_ids", None)
        if changes:
            await view_repo.update(view_id, **changes)
        if category_ids is not None:
            await view_repo.set_categories(view_id, category_ids)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    view = await view_repo.get_with_categories(view_id)
    return BudgetViewResponse.model_validate(view)


@router.delete("/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_view(
    view_id: ViewAccess,
    current_user: CurrentUser,
    view_repo: Annotated[BudgetViewRepository, Depends(get_budget_view_repo)],
) -> None:
    try:
        await view_repo.soft_delete(view_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
