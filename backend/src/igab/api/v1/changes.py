import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.change import (
    ChangeListResponse,
    ChangeOut,
    UndoLatestResult,
    UndoResult,
)
from igab.dependencies import (
    BudgetAccess,
    CurrentUser,
    get_change_log_repo,
    get_undo_service,
)
from igab.domain.exceptions import NotFoundError, UndoConflict
from igab.repositories.change_log_repo import ChangeLogRepository
from igab.services.undo_service import UndoService

router = APIRouter(route_class=CommitRoute)


@router.get("/{budget_id}/changes", response_model=ChangeListResponse)
async def list_changes(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    change_repo: Annotated[ChangeLogRepository, Depends(get_change_log_repo)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ChangeListResponse:
    changes = await change_repo.list_for_budget(budget_id, limit=limit, offset=offset)
    total = await change_repo.count_for_budget(budget_id)
    names = await change_repo.display_names([c for c, _ in changes])
    return ChangeListResponse(
        changes=[
            ChangeOut.model_validate(c).model_copy(update={"user_display_name": label})
            for c, label in changes
        ],
        total=total,
        names=names,
    )


def _conflict(e: UndoConflict) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"message": str(e), "fields": e.fields},
    )


@router.post("/{budget_id}/changes/undo", response_model=UndoLatestResult)
async def undo_latest(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    undo_service: Annotated[UndoService, Depends(get_undo_service)],
) -> UndoLatestResult:
    """Undo the newest live manual change — ⌘Z's target. The server picks:
    the client used to select from a 20-row window it fetched separately,
    which raced background writers (a sync landing mid-⌘Z got undone) and
    starved on a page of already-undone rows. Import/system/AI rows are
    skipped — they keep their own undo surfaces."""
    try:
        candidate, undone = await undo_service.undo_latest(budget_id)
    except UndoConflict as e:
        raise _conflict(e) from e
    return UndoLatestResult(
        undone_change_ids=undone,
        action=candidate.action,
        entity_type=candidate.entity_type,
    )


@router.post("/{budget_id}/changes/{change_id}/undo", response_model=UndoResult)
async def undo_change(
    budget_id: BudgetAccess,
    change_id: uuid.UUID,
    current_user: CurrentUser,
    undo_service: Annotated[UndoService, Depends(get_undo_service)],
    force: bool = Query(False),
) -> UndoResult:
    try:
        undone = await undo_service.undo_change(budget_id, change_id, force=force)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except UndoConflict as e:
        raise _conflict(e) from e
    return UndoResult(undone_change_ids=undone)


@router.post("/{budget_id}/changes/redo", response_model=UndoResult)
async def redo_latest(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    undo_service: Annotated[UndoService, Depends(get_undo_service)],
    force: bool = Query(False),
) -> UndoResult:
    """Re-apply the most recently undone change or batch. Refused once
    anything newer has been recorded."""
    try:
        redone = await undo_service.redo_latest(budget_id, force=force)
    except UndoConflict as e:
        raise _conflict(e) from e
    return UndoResult(undone_change_ids=redone)


@router.post("/{budget_id}/changes/{change_id}/undo-newer", response_model=UndoResult)
async def undo_newer(
    budget_id: BudgetAccess,
    change_id: uuid.UUID,
    current_user: CurrentUser,
    undo_service: Annotated[UndoService, Depends(get_undo_service)],
    force: bool = Query(False),
    dry_run: bool = Query(False),
) -> UndoResult:
    """Undo everything recorded after this change; this change survives.

    The Activity page's "revert to here" line, which sits between two
    entries — so the id sent is the newest entry below the line. `dry_run`
    reports what would go without writing, so the confirmation prompt counts
    with the same query that does the work.
    """
    try:
        undone = await undo_service.undo_newer(budget_id, change_id, force=force, dry_run=dry_run)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except UndoConflict as e:
        raise _conflict(e) from e
    return UndoResult(undone_change_ids=undone)


@router.post("/{budget_id}/budget/moves/{move_id}/undo", response_model=UndoResult)
async def undo_move(
    budget_id: BudgetAccess,
    move_id: uuid.UUID,
    current_user: CurrentUser,
    undo_service: Annotated[UndoService, Depends(get_undo_service)],
) -> UndoResult:
    """Undo one budget move on its own — even one that shares a batch with
    a bulk assign's other moves."""
    try:
        undone = await undo_service.undo_move(budget_id, move_id)
    except UndoConflict as e:
        raise _conflict(e) from e
    return UndoResult(undone_change_ids=undone)


@router.post("/{budget_id}/changes/batch/{batch_id}/undo", response_model=UndoResult)
async def undo_batch(
    budget_id: BudgetAccess,
    batch_id: uuid.UUID,
    current_user: CurrentUser,
    undo_service: Annotated[UndoService, Depends(get_undo_service)],
    force: bool = Query(False),
) -> UndoResult:
    try:
        undone = await undo_service.undo_batch(budget_id, batch_id, force=force)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except UndoConflict as e:
        raise _conflict(e) from e
    return UndoResult(undone_change_ids=undone)
