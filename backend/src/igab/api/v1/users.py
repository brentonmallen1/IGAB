"""User management. Listing is open to any authenticated user (the budget
sharing picker needs names); mutations are admin-only.

There is deliberately NO hard delete: users.id cascades into budgets, so
deleting a user would take every budget they created — shared or not — with
them. Deactivation covers the real need (revoking access) and existing tokens
die at the next lookup because the user repo filters is_active.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.api.route import CommitRoute
from igab.api.v1.schemas.auth import UserCreateRequest, UserListItem, UserUpdateRequest
from igab.config import settings as app_settings
from igab.db.models import User
from igab.db.session import get_session
from igab.dependencies import AdminUser, CurrentUser, get_auth_service
from igab.domain.exceptions import DuplicateError
from igab.services.auth_service import AuthService, hash_password

router = APIRouter(route_class=CommitRoute)


def _to_item(user: User) -> UserListItem:
    return UserListItem.model_validate(user).model_copy(
        update={"is_env_admin": user.email == app_settings.ADMIN_EMAIL}
    )


@router.get("/users", response_model=list[UserListItem])
async def list_users(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[UserListItem]:
    """All users, active first. Open to every authenticated user — a budget
    owner needs the household roster to share with (acceptable for the
    app's small-household audience)."""
    result = await session.execute(select(User).order_by(User.is_active.desc(), User.created_at))
    return [_to_item(u) for u in result.scalars().all()]


# User CRUD is deliberately absent from the change log (see change_log.py's
# exclusion list): accounts are server administration with no budget to file
# under, and change_log.budget_id is NOT NULL by design.
@router.post("/users", response_model=UserListItem, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    current_user: AdminUser,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserListItem:
    try:
        user = await auth_service.create_user(
            email=body.email, password=body.password, display_name=body.display_name
        )
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return _to_item(user)


@router.patch("/users/{user_id}", response_model=UserListItem)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    current_user: AdminUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserListItem:
    """Admin edits: display name, activation, password reset.

    Guards: the admin cannot deactivate themself (an instance must never go
    adminless), and the env-managed ADMIN_EMAIL account cannot be deactivated
    or password-reset here — ADMIN_PASSWORD owns that credential and boot
    would revert any reset anyway.
    """
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    is_env_admin = user.email == app_settings.ADMIN_EMAIL
    if body.is_active is False:
        if user.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account.",
            )
        if is_env_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The bootstrap admin account cannot be deactivated.",
            )
    if body.password is not None and is_env_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The admin credential is managed by the ADMIN_PASSWORD"
            " environment variable — change it there and restart.",
        )

    if body.display_name is not None:
        user.display_name = body.display_name.strip() or None
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    await session.flush()
    return _to_item(user)
