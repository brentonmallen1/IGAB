from pydantic import BaseModel


class SettingUpdate(BaseModel):
    value: str


class SettingResponse(BaseModel):
    key: str
    value: str | None
    # Whether a stored override exists (vs env/default). None on legacy paths.
    is_overridden: bool | None = None
    default_value: str | None = None


class UpdateStatusResponse(BaseModel):
    enabled: bool
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str | None = None
