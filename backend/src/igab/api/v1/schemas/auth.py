import uuid

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str | None = None


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None
    #: Admin password reset — sets a new password without knowing the old one.
    password: str | None = Field(default=None, min_length=8)


class UserListItem(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool
    is_active: bool
    #: Matches ADMIN_EMAIL — this account's credential is env-managed, so the
    #: UI hides reset/deactivate instead of offering dead ends.
    is_env_admin: bool = False

    model_config = {"from_attributes": True}
