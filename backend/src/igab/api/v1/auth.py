from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserResponse
from igab.dependencies import CurrentUser, get_auth_service
from igab.domain.exceptions import AuthenticationError
from igab.services.auth_service import AuthService

router = APIRouter()


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
