from typing import Annotated

from fastapi import APIRouter, Depends

from igab.api.v1.schemas.settings import UpdateStatusResponse
from igab.dependencies import CurrentUser, get_settings_service
from igab.services import update_service
from igab.services.settings_service import SettingsService

router = APIRouter()


@router.get("/system/update-status", response_model=UpdateStatusResponse)
async def get_update_status(
    current_user: CurrentUser,
    svc: Annotated[SettingsService, Depends(get_settings_service)],
) -> UpdateStatusResponse:
    """Opt-in update check. With update_check_enabled off (the default) this
    answers from local state only — GitHub is never contacted."""
    current = update_service.current_version()
    enabled = (await svc.get("update_check_enabled")) == "true"
    if not enabled:
        return UpdateStatusResponse(enabled=False, current_version=current)
    latest, url = await update_service.fetch_latest_release()
    return UpdateStatusResponse(
        enabled=True,
        current_version=current,
        latest_version=latest,
        update_available=update_service.is_newer(latest, current),
        release_url=url,
    )
