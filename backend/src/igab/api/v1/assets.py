"""Assets: things the household owns whose worth is stated and dated.

The value endpoints are near-copies of the liability balance-snapshot ones,
minus that endpoint's managed-liability refusal — it has no analogue here,
because an asset is never account-backed: a house has no transactions, and
"it appraised higher" is a dated statement, not a ledger row.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.asset import (
    AssetCreate,
    AssetOut,
    AssetUpdate,
    AssetValueCreate,
    AssetValueOut,
    AssetValueUpdate,
)
from igab.db.models import Asset
from igab.dependencies import BudgetAccess, CurrentUser, SessionDep
from igab.repositories.asset_repo import AssetRepository
from igab.utils.clock import recorded_on

router = APIRouter(route_class=CommitRoute)


def _repo(session: SessionDep) -> AssetRepository:
    return AssetRepository(session)


RepoDep = Annotated[AssetRepository, Depends(_repo)]


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
    budget_id: BudgetAccess, body: AssetCreate, current_user: CurrentUser, repo: RepoDep
) -> AssetOut:
    asset = await repo.create(budget_id=budget_id, name=body.name, asset_type=body.asset_type)
    if body.value is not None:
        await repo.upsert_value(asset, recorded_on(body.value_as_of, body.client_today), body.value)
        # updated_at is onupdate=func.now(); the flush expired it, and
        # lazy-loading it during serialization is sync-context IO.
        await repo.session.refresh(asset)
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
) -> AssetOut:
    asset = await _owned(repo, budget_id, asset_id)
    if body.name is not None:
        asset.name = body.name
    if body.asset_type is not None:
        asset.asset_type = body.asset_type
    return _out(asset)


@router.delete("/{budget_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    budget_id: BudgetAccess, asset_id: uuid.UUID, current_user: CurrentUser, repo: RepoDep
) -> None:
    asset = await _owned(repo, budget_id, asset_id)
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
) -> AssetValueOut:
    asset = await _owned(repo, budget_id, asset_id)
    snapshot = await repo.upsert_value(asset, recorded_on(body.date, body.client_today), body.value)
    return AssetValueOut.model_validate(snapshot)


@router.patch("/{budget_id}/assets/{asset_id}/values/{value_id}", response_model=AssetValueOut)
async def edit_value(
    budget_id: BudgetAccess,
    asset_id: uuid.UUID,
    value_id: uuid.UUID,
    body: AssetValueUpdate,
    current_user: CurrentUser,
    repo: RepoDep,
) -> AssetValueOut:
    asset = await _owned(repo, budget_id, asset_id)
    snapshot = await repo.update_value(asset, value_id, body.value)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Value point not found")
    return AssetValueOut.model_validate(snapshot)


@router.delete(
    "/{budget_id}/assets/{asset_id}/values/{value_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_value(
    budget_id: BudgetAccess,
    asset_id: uuid.UUID,
    value_id: uuid.UUID,
    current_user: CurrentUser,
    repo: RepoDep,
) -> None:
    asset = await _owned(repo, budget_id, asset_id)
    if not await repo.delete_value(asset, value_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Value point not found")


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
