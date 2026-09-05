"""Assets: things the household owns whose worth is stated and dated.

The value endpoints are near-copies of the liability balance-snapshot ones,
minus that endpoint's managed-liability refusal — it has no analogue here,
because an asset is never account-backed: a house has no transactions, and
"it appraised higher" is a dated statement, not a ledger row.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from igab.api.route import CommitRoute
from igab.api.v1.schemas.asset import (
    AssetCreate,
    AssetOut,
    AssetUpdate,
    AssetValueCreate,
    AssetValueOut,
    AssetValueUpdate,
)
from igab.db.models import Asset, Liability
from igab.dependencies import BudgetAccess, CurrentUser, SessionDep, get_change_recorder
from igab.repositories.asset_repo import AssetRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match
from igab.utils.clock import recorded_on

router = APIRouter(route_class=CommitRoute)


def _repo(session: SessionDep) -> AssetRepository:
    return AssetRepository(session)


RepoDep = Annotated[AssetRepository, Depends(_repo)]
Recorder = Annotated[ChangeRecorder, Depends(get_change_recorder)]


async def _record_derived_move(
    recorder: ChangeRecorder, budget_id: uuid.UUID, asset: Asset, before: dict
) -> None:
    """A value-point operation drags (`manual_value`, `value_as_of`) along;
    recording the pair's move as an explicit asset update in the same batch
    is what lets undo restore it by field instead of re-deriving."""
    after = snapshot("asset", asset)
    if snapshots_match(after, before):  # non-empty diff — the pair moved
        await recorder.record(
            budget_id=budget_id,
            entity_type="asset",
            entity_id=asset.id,
            action="update",
            before=before,
            after=after,
        )


async def _owned(repo: AssetRepository, budget_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    asset = await repo.get(asset_id)
    if asset is None or asset.budget_id != budget_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


@router.get("/{budget_id}/assets", response_model=list[AssetOut])
async def list_assets(
    budget_id: BudgetAccess, current_user: CurrentUser, repo: RepoDep
) -> list[AssetOut]:
    return [_out(a) for a in await repo.get_all(budget_id)]


@router.post("/{budget_id}/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(
    budget_id: BudgetAccess,
    body: AssetCreate,
    current_user: CurrentUser,
    repo: RepoDep,
    recorder: Recorder,
) -> AssetOut:
    # One batch: an asset born with a value undoes as a unit.
    with recorder.batch():
        asset = await repo.create(budget_id=budget_id, name=body.name, asset_type=body.asset_type)
        seeded = None
        if body.value is not None:
            seeded = await repo.upsert_value(
                asset, recorded_on(body.value_as_of, body.client_today), body.value
            )
            # updated_at is onupdate=func.now(); the flush expired it, and
            # lazy-loading it during serialization is sync-context IO.
            await repo.session.refresh(asset)
        if seeded is not None:
            await recorder.record(
                budget_id=budget_id,
                entity_type="asset_value",
                entity_id=seeded.id,
                action="create",
                after=snapshot("asset_value", seeded),
            )
        # The asset records last: ⌘Z's toast names a batch's newest row, and
        # "create asset" is what the person did.
        await recorder.record(
            budget_id=budget_id,
            entity_type="asset",
            entity_id=asset.id,
            action="create",
            after=snapshot("asset", asset),
        )
    return _out(asset)


@router.get("/{budget_id}/assets/{asset_id}", response_model=AssetOut)
async def get_asset(
    budget_id: BudgetAccess, asset_id: uuid.UUID, current_user: CurrentUser, repo: RepoDep
) -> AssetOut:
    return _out(await _owned(repo, budget_id, asset_id))


@router.patch("/{budget_id}/assets/{asset_id}", response_model=AssetOut)
async def update_asset(
    budget_id: BudgetAccess,
    asset_id: uuid.UUID,
    body: AssetUpdate,
    current_user: CurrentUser,
    repo: RepoDep,
    recorder: Recorder,
) -> AssetOut:
    asset = await _owned(repo, budget_id, asset_id)
    before = snapshot("asset", asset)
    if body.name is not None:
        asset.name = body.name
    if body.asset_type is not None:
        asset.asset_type = body.asset_type
    after = snapshot("asset", asset)
    if snapshots_match(after, before):  # non-empty diff — something changed
        await recorder.record(
            budget_id=budget_id,
            entity_type="asset",
            entity_id=asset.id,
            action="update",
            before=before,
            after=after,
        )
    return _out(asset)


@router.delete("/{budget_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    budget_id: BudgetAccess,
    asset_id: uuid.UUID,
    current_user: CurrentUser,
    repo: RepoDep,
    recorder: Recorder,
) -> None:
    asset = await _owned(repo, budget_id, asset_id)
    # `_liability_ids` names the debts the retire is about to unlink, so undo
    # can re-point exactly those — and only ones still loose.
    secured = (
        (
            await repo.session.execute(
                select(Liability.id).where(Liability.linked_asset_id == asset.id)
            )
        )
        .scalars()
        .all()
    )
    await recorder.record(
        budget_id=budget_id,
        entity_type="asset",
        entity_id=asset.id,
        action="delete",
        before={
            **snapshot("asset", asset),
            "_liability_ids": [str(x) for x in secured],
        },
    )
    # retire, not soft_delete: the unlink of secured liabilities is not
    # optional — SET NULL never fires on a soft delete.
    await repo.retire(asset)


@router.get("/{budget_id}/assets/{asset_id}/values", response_model=list[AssetValueOut])
async def list_values(
    budget_id: BudgetAccess, asset_id: uuid.UUID, current_user: CurrentUser, repo: RepoDep
) -> list[AssetValueOut]:
    """The value register, newest first — the piece the liability side never
    had: its snapshots are written and never listed, so an entered balance is
    unreviewable there. This is the template."""
    asset = await _owned(repo, budget_id, asset_id)
    return [AssetValueOut.model_validate(v) for v in await repo.get_values(asset.id)]


@router.post(
    "/{budget_id}/assets/{asset_id}/values",
    response_model=AssetValueOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_value(
    budget_id: BudgetAccess,
    asset_id: uuid.UUID,
    body: AssetValueCreate,
    current_user: CurrentUser,
    repo: RepoDep,
    recorder: Recorder,
) -> AssetValueOut:
    asset = await _owned(repo, budget_id, asset_id)
    value_date = recorded_on(body.date, body.client_today)
    # One batch: the point and the derived pair it drags along undo as a
    # unit. A second entry on the same date replaces the first, so the
    # record is an update with the replaced figure as `before`.
    with recorder.batch():
        existing = next((v for v in await repo.get_values(asset.id) if v.date == value_date), None)
        point_before = snapshot("asset_value", existing) if existing is not None else None
        asset_before = snapshot("asset", asset)
        point = await repo.upsert_value(asset, value_date, body.value)
        point_after = snapshot("asset_value", point)
        # Derived pair first, point last: ⌘Z's toast names a batch's newest
        # row, and "add a value point" is what the person did.
        await _record_derived_move(recorder, budget_id, asset, asset_before)
        if point_before is None:
            await recorder.record(
                budget_id=budget_id,
                entity_type="asset_value",
                entity_id=point.id,
                action="create",
                after=point_after,
            )
        elif snapshots_match(point_after, point_before):
            await recorder.record(
                budget_id=budget_id,
                entity_type="asset_value",
                entity_id=point.id,
                action="update",
                before=point_before,
                after=point_after,
            )
    return AssetValueOut.model_validate(point)


@router.patch("/{budget_id}/assets/{asset_id}/values/{value_id}", response_model=AssetValueOut)
async def edit_value(
    budget_id: BudgetAccess,
    asset_id: uuid.UUID,
    value_id: uuid.UUID,
    body: AssetValueUpdate,
    current_user: CurrentUser,
    repo: RepoDep,
    recorder: Recorder,
) -> AssetValueOut:
    asset = await _owned(repo, budget_id, asset_id)
    with recorder.batch():
        existing = next((v for v in await repo.get_values(asset.id) if v.id == value_id), None)
        point_before = snapshot("asset_value", existing) if existing is not None else None
        asset_before = snapshot("asset", asset)
        point = await repo.update_value(asset, value_id, body.value)
        if point is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Value point not found"
            )
        point_after = snapshot("asset_value", point)
        await _record_derived_move(recorder, budget_id, asset, asset_before)
        if point_before is not None and snapshots_match(point_after, point_before):
            await recorder.record(
                budget_id=budget_id,
                entity_type="asset_value",
                entity_id=point.id,
                action="update",
                before=point_before,
                after=point_after,
            )
    return AssetValueOut.model_validate(point)


@router.delete(
    "/{budget_id}/assets/{asset_id}/values/{value_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_value(
    budget_id: BudgetAccess,
    asset_id: uuid.UUID,
    value_id: uuid.UUID,
    current_user: CurrentUser,
    repo: RepoDep,
    recorder: Recorder,
) -> None:
    asset = await _owned(repo, budget_id, asset_id)
    with recorder.batch():
        existing = next((v for v in await repo.get_values(asset.id) if v.id == value_id), None)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Value point not found"
            )
        point_before = snapshot("asset_value", existing)
        asset_before = snapshot("asset", asset)
        point_id = existing.id
        if not await repo.delete_value(asset, value_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Value point not found"
            )
        await _record_derived_move(recorder, budget_id, asset, asset_before)
        await recorder.record(
            budget_id=budget_id,
            entity_type="asset_value",
            entity_id=point_id,
            action="delete",
            before=point_before,
        )


def _out(asset: Asset) -> AssetOut:
    return AssetOut(
        id=asset.id,
        budget_id=asset.budget_id,
        name=asset.name,
        asset_type=asset.asset_type,
        current_value=asset.manual_value,
        value_as_of=asset.value_as_of,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )
