import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.v1.schemas.settings import SettingResponse, SettingUpdate
from igab.dependencies import AdminUser, CurrentUser, get_settings_service
from igab.services.ai_prompts import DEFAULT_PROMPTS
from igab.services.ai_service import invalidate_capabilities
from igab.services.settings_service import SettingsService

router = APIRouter()

EDITABLE_KEYS = {
    "ai_enabled",
    "ollama_host",
    "ollama_model",
    "ollama_vision_model",
    "ai_thinking",
    "ollama_options",
    "ollama_vision_options",
    "ai_vision_timeout_s",
    "backup_interval_hours",
    "backup_keep_days",
    "backup_keep_min",
    "backup_age_recipient",
    "update_check_enabled",
    *DEFAULT_PROMPTS.keys(),
}

# The backup agent clamps to these same bounds — a settings UI must not be
# able to configure backups into not happening.
_BACKUP_INT_BOUNDS = {
    "backup_interval_hours": (1, 168),
    "backup_keep_days": (1, 365),
    "backup_keep_min": (1, 100),
}


# Settings that change which model the vision capability probe describes. A
# stale probe outlives the fix that made it wrong, so drop it on any write.
_CAPABILITY_KEYS = {"ollama_host", "ollama_model", "ollama_vision_model"}


def _validate_setting(key: str, value: str) -> None:
    if key in ("ollama_options", "ollama_vision_options"):
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{key} must be valid JSON",
            )
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{key} must be a JSON object",
            )
    elif key == "ai_vision_timeout_s":
        if not value.isdigit() or int(value) <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="ai_vision_timeout_s must be a positive integer",
            )
    elif key == "ai_thinking":
        if value not in ("auto", "on", "off"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="ai_thinking must be one of: auto, on, off",
            )
    elif key in _BACKUP_INT_BOUNDS:
        lo, hi = _BACKUP_INT_BOUNDS[key]
        if not value.isdigit() or not lo <= int(value) <= hi:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{key} must be an integer between {lo} and {hi}",
            )
    elif key in ("update_check_enabled", "ai_enabled"):
        if value not in ("true", "false"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{key} must be 'true' or 'false'",
            )
    elif key == "backup_age_recipient":
        if value and not re.fullmatch(r"age1[0-9a-z]+", value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="backup_age_recipient must be an age public key (age1...) or empty",
            )


@router.get("/settings", response_model=list[SettingResponse])
async def get_settings(
    current_user: CurrentUser,
    svc: Annotated[SettingsService, Depends(get_settings_service)],
) -> list[SettingResponse]:
    detailed = await svc.get_all_detailed()
    return [SettingResponse(**item) for item in detailed]


# Writes are admin-gated: app_settings is a household-global singleton
# (AI config, backup schedule) — a member mis-tap must not reconfigure the
# server. Reads stay open: every client needs the values.
@router.put("/settings/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    body: SettingUpdate,
    current_user: AdminUser,
    svc: Annotated[SettingsService, Depends(get_settings_service)],
) -> SettingResponse:
    if key not in EDITABLE_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Setting '{key}' is not editable via API",
        )
    _validate_setting(key, body.value)
    await svc.set(key, body.value)
    if key in _CAPABILITY_KEYS:
        invalidate_capabilities()
    return SettingResponse(key=key, value=body.value, is_overridden=True)


@router.delete("/settings/{key}", response_model=SettingResponse)
async def reset_setting(
    key: str,
    current_user: AdminUser,
    svc: Annotated[SettingsService, Depends(get_settings_service)],
) -> SettingResponse:
    """Remove the stored override; the setting reverts to its env/default value."""
    if key not in EDITABLE_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Setting '{key}' is not editable via API",
        )
    await svc.unset(key)
    if key in _CAPABILITY_KEYS:
        invalidate_capabilities()
    effective = await svc.get(key)
    return SettingResponse(key=key, value=effective, is_overridden=False)
