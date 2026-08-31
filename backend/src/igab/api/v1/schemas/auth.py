import uuid

from pydantic import EmailStr, Field

from igab.api.v1.schemas.base import ApiModel


class LoginRequest(ApiModel):
    email: EmailStr
    password: str


class TokenResponse(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(ApiModel):
    refresh_token: str


class UserResponse(ApiModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool

    model_config = {"from_attributes": True}


class ChangePasswordRequest(ApiModel):
    current_password: str
    new_password: str = Field(min_length=8)


class UserCreateRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str | None = None


class UserUpdateRequest(ApiModel):
    display_name: str | None = None
    is_active: bool | None = None
    #: Admin password reset — sets a new password without knowing the old one.
    password: str | None = Field(default=None, min_length=8)


class UserListItem(ApiModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool
    is_active: bool
    #: Matches ADMIN_EMAIL — this account's credential is env-managed, so the
    #: UI hides reset/deactivate instead of offering dead ends.
    is_env_admin: bool = False

    model_config = {"from_attributes": True}
