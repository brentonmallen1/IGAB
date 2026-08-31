from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from igab.dependencies import CurrentUser, get_auth_service
from igab.domain.exceptions import AuthenticationError
from igab.services.auth_service import AuthService

router = APIRouter(route_class=CommitRoute)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    try:
        access_token, refresh_token = await auth_service.login(body.email, body.password)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    try:
        access_token = await auth_service.refresh(body.refresh_token)
        return TokenResponse(access_token=access_token, refresh_token=body.refresh_token)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """Self-service password change.

    The env-managed admin is refused: ADMIN_PASSWORD re-syncs the hash at
    every boot, so an in-app change would be silently reverted — better an
    honest 403 than a password that stops working at the next restart.
    """
    from igab.config import settings as app_settings

    if current_user.email == app_settings.ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The admin credential is managed by the ADMIN_PASSWORD"
            " environment variable — change it there and restart.",
        )
    try:
        await auth_service.change_password(current_user, body.current_password, body.new_password)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
