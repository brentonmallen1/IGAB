"""Creating and revoking the read-only keys an assistant connects with."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from igab.api.route import CommitRoute
from igab.api.v1.schemas.base import ApiModel
from igab.db.models import ApiKey
from igab.dependencies import CurrentUser, _is_member, get_session
from igab.services import api_key_service

router = APIRouter(route_class=CommitRoute)


class ApiKeyOut(ApiModel):
    """One key as its owner sees it afterwards.

    No field here can reconstruct the key. `prefix` is enough to tell two
    apart in a list and nothing more, which is the whole point of storing
    only a hash.
    """

    id: uuid.UUID
    name: str
    prefix: str
    scopes: str
    budget_ids: list[uuid.UUID]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    #: The only time this is ever returned. Not recoverable afterwards — the
    #: server kept a hash, exactly as it does for a password.
    key: str


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    #: At least one. A key scoped to nothing could authenticate and read
    #: nothing, which is a confusing way to spend an afternoon.
    budget_ids: list[uuid.UUID] = Field(min_length=1)


def _as_out(key: ApiKey) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "scopes": key.scopes,
        "budget_ids": [link.budget_id for link in key.budgets],
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
    }


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """This user's keys, revoked ones included.

    Revoked keys stay listed: a key that turns up in someone's config or a
    log needs to be identifiable after it stops working.
    """
    rows = (
        (
            await session.execute(
                select(ApiKey)
                .where(ApiKey.user_id == current_user.id)
                .options(selectinload(ApiKey.budgets))
                .order_by(ApiKey.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_as_out(key) for key in rows]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Mint a key and show it once.

    Every named budget is checked against the caller's own membership: a key
    can never reach further than the person who made it.
    """
    for budget_id in payload.budget_ids:
        allowed = await session.scalar(select(_is_member(budget_id, current_user.id)))
        if not allowed:
            # Not found rather than forbidden — distinguishing them would say
            # which budget ids exist.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Budget not found",
            )

    key, raw = await api_key_service.create_key(
        session,
        user_id=current_user.id,
        name=payload.name.strip(),
        budget_ids=payload.budget_ids,
    )
    await session.refresh(key, attribute_names=["budgets", "created_at"])
    return {**_as_out(key), "key": raw}


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Stop a key working. Idempotent: revoking twice is not an error."""
    key = (
        await session.execute(
            select(ApiKey)
            .where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
            .options(selectinload(ApiKey.budgets))
        )
    ).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    if key.revoked_at is None:
        await api_key_service.revoke(session, key)
