from igab.api.v1.schemas.base import ApiModel


class SettingUpdate(ApiModel):
    value: str


class SettingResponse(ApiModel):
    key: str
    value: str | None
    # Whether a stored override exists (vs env/default). None on legacy paths.
    is_overridden: bool | None = None
    default_value: str | None = None
    # Prompt settings only: the {placeholders} the template may use. Served
    # from the one registry in ai_prompts so the settings UI never keeps a copy.
    placeholders: list[str] | None = None


class UpdateStatusResponse(ApiModel):
    enabled: bool
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str | None = None
