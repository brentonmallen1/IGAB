from typing import Annotated

from fastapi import APIRouter, Depends

from igab.api.v1.schemas.settings import SettingResponse, SettingUpdate
from igab.dependencies import CurrentUser, get_settings_service
from igab.services.settings_service import SettingsService

router = APIRouter()

EDITABLE_KEYS = {"ollama_host", "ollama_model"}


@router.get("/settings", response_model=list[SettingResponse])
async def get_settings(
    current_user: CurrentUser,
    svc: Annotated[SettingsService, Depends(get_settings_service)],
) -> list[SettingResponse]:
    all_settings = await svc.get_all()
    return [SettingResponse(key=k, value=v) for k, v in all_settings.items()]


@router.put("/settings/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    body: SettingUpdate,
    current_user: CurrentUser,
    svc: Annotated[SettingsService, Depends(get_settings_service)],
) -> SettingResponse:
    from fastapi import HTTPException, status

    if key not in EDITABLE_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Setting '{key}' is not editable via API",
        )
    await svc.set(key, body.value)
    return SettingResponse(key=key, value=body.value)
