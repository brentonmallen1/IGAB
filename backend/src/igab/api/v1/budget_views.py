from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.budget_view import (
    BudgetViewCreate,
    BudgetViewResponse,
    BudgetViewUpdate,
)
from igab.dependencies import (
    BudgetAccess,
    CurrentUser,
    ViewAccess,
    get_budget_view_repo,
    get_change_recorder,
)
from igab.domain.exceptions import NotFoundError
from igab.repositories.budget_view_repo import BudgetViewRepository
from igab.services.change_log import ChangeRecorder, snapshot, view_children_dump

router = APIRouter(route_class=CommitRoute)


ViewRepo = Annotated[BudgetViewRepository, Depends(get_budget_view_repo)]
Recorder = Annotated[ChangeRecorder, Depends(get_change_recorder)]


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
    recorder: Recorder,
) -> BudgetViewResponse:
    # Name collisions become a 409 via the IntegrityError handler in main,
    # which reads the constraint that actually failed. Catching it here meant
    # a duplicate PLACEMENT was reported as 'a view named "" already exists'.
    view = await repo.create(
        budget_id=budget_id, name=body.name, hide_unassigned=body.hide_unassigned
    )
    # Groups first: placements may reference them by name.
    if body.groups:
        await repo.set_groups(view.id, body.groups)
    if body.placements:
        await repo.set_placements(view.id, [p.model_dump() for p in body.placements])
    await recorder.record(
        budget_id=budget_id,
        entity_type="budget_view",
        entity_id=view.id,
        action="create",
        after=snapshot("budget_view", view),
    )
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
    recorder: Recorder,
) -> BudgetViewResponse:
    existing = await repo.get_full(view_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    # Children ride the record as bookkeeping dumps: they are hard-replaced
    # rows, so an undo has to rebuild them rather than flip fields back.
    before = {
        **snapshot("budget_view", existing),
        **view_children_dump(existing.groups, existing.placements),
    }
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
    view = await repo.get_full(view_id)
    if view is None:
        # The guard filters is_deleted too, so this is a mid-request delete —
        # still a 404, never model_validate(None) → 500.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    # The up-front get_full loaded the child collections into the identity
    # map, and a re-select does not repopulate them — without this refresh
    # both the response and the recorded `after` would show the OLD children.
    await repo.session.refresh(view, ["groups", "placements"])
    after = {
        **snapshot("budget_view", view),
        **view_children_dump(view.groups, view.placements),
    }
    if before != after:  # a scalar or a child moved (no decimals here, == is exact)
        await recorder.record(
            budget_id=view.budget_id,
            entity_type="budget_view",
            entity_id=view.id,
            action="update",
            before=before,
            after=after,
        )
    return BudgetViewResponse.model_validate(view)


@router.delete("/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_view(
    view_id: ViewAccess, current_user: CurrentUser, repo: ViewRepo, recorder: Recorder
) -> None:
    try:
        view = await repo.get_full(view_id)
        if view is not None:
            # A soft delete leaves the children in place, so the snapshot
            # alone is the whole inverse.
            await recorder.record(
                budget_id=view.budget_id,
                entity_type="budget_view",
                entity_id=view.id,
                action="delete",
                before=snapshot("budget_view", view),
            )
        await repo.soft_delete(view_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
