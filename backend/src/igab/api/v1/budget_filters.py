from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.budget_filter import (
    BudgetFilterCreate,
    BudgetFilterResponse,
    BudgetFilterUpdate,
)
from igab.dependencies import (
    BudgetAccess,
    CurrentUser,
    FilterAccess,
    get_budget_filter_repo,
    get_change_recorder,
)
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.repositories.budget_filter_repo import BudgetFilterRepository
from igab.services.change_log import ChangeRecorder, filter_selection_dump, snapshot

router = APIRouter(route_class=CommitRoute)

Recorder = Annotated[ChangeRecorder, Depends(get_change_recorder)]


@router.get("/{budget_id}/filters", response_model=list[BudgetFilterResponse])
async def list_budget_filters(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
) -> list[BudgetFilterResponse]:
    filters = await filter_repo.get_all(budget_id)
    effective = await filter_repo.effective_category_ids(filters)
    return [BudgetFilterResponse.from_row(f, effective[f.id]) for f in filters]


@router.post(
    "/{budget_id}/filters",
    response_model=BudgetFilterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_budget_filter(
    budget_id: BudgetAccess,
    body: BudgetFilterCreate,
    current_user: CurrentUser,
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
    recorder: Recorder,
) -> BudgetFilterResponse:
    created = await filter_repo.create(budget_id=budget_id, name=body.name)
    await filter_repo.set_categories(created.id, body.category_ids)
    try:
        await filter_repo.set_tags(created.id, body.tag_ids)
    except InvariantViolation as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await recorder.record(
        budget_id=budget_id,
        entity_type="budget_filter",
        entity_id=created.id,
        action="create",
        after=snapshot("budget_filter", created),
    )
    return await _respond(filter_repo, created.id)


async def _respond(filter_repo: BudgetFilterRepository, filter_id) -> BudgetFilterResponse:
    row = await filter_repo.get_with_categories(filter_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filter not found")
    effective = await filter_repo.effective_category_ids([row])
    return BudgetFilterResponse.from_row(row, effective[row.id])


@router.get("/filters/{filter_id}", response_model=BudgetFilterResponse)
async def get_budget_filter(
    filter_id: FilterAccess,
    current_user: CurrentUser,
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
) -> BudgetFilterResponse:
    return await _respond(filter_repo, filter_id)


@router.patch("/filters/{filter_id}", response_model=BudgetFilterResponse)
async def update_budget_filter(
    filter_id: FilterAccess,
    body: BudgetFilterUpdate,
    current_user: CurrentUser,
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
    recorder: Recorder,
) -> BudgetFilterResponse:
    existing = await filter_repo.get_with_categories(filter_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filter not found")
    # The selection rides the record as a bookkeeping dump: its rows are
    # hard-replaced, so an undo rebuilds them rather than flipping fields.
    before = {
        **snapshot("budget_filter", existing),
        **filter_selection_dump(existing.category_selections, existing.tag_selections),
    }
    try:
        changes = body.model_dump(exclude_none=True)
        category_ids = changes.pop("category_ids", None)
        tag_ids = changes.pop("tag_ids", None)
        if changes:
            await filter_repo.update(filter_id, **changes)
        if category_ids is not None:
            await filter_repo.set_categories(filter_id, category_ids)
        if tag_ids is not None:
            await filter_repo.set_tags(filter_id, tag_ids)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except InvariantViolation as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    updated = await filter_repo.get_with_categories(filter_id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filter not found")
    # See update_budget_view: the identity map keeps the pre-change child
    # collection loaded; refresh or the response and record show old rows.
    await filter_repo.session.refresh(updated, ["category_selections", "tag_selections"])
    after = {
        **snapshot("budget_filter", updated),
        **filter_selection_dump(updated.category_selections, updated.tag_selections),
    }
    if before != after:  # a scalar or the selection moved (no decimals, == is exact)
        await recorder.record(
            budget_id=updated.budget_id,
            entity_type="budget_filter",
            entity_id=updated.id,
            action="update",
            before=before,
            after=after,
        )
    return await _respond(filter_repo, filter_id)


@router.delete("/filters/{filter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_filter(
    filter_id: FilterAccess,
    current_user: CurrentUser,
    filter_repo: Annotated[BudgetFilterRepository, Depends(get_budget_filter_repo)],
    recorder: Recorder,
) -> None:
    try:
        found = await filter_repo.get_with_categories(filter_id)
        if found is not None:
            # A soft delete leaves the selection rows in place, so the
            # snapshot alone is the whole inverse.
            await recorder.record(
                budget_id=found.budget_id,
                entity_type="budget_filter",
                entity_id=found.id,
                action="delete",
                before=snapshot("budget_filter", found),
            )
        await filter_repo.soft_delete(filter_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
