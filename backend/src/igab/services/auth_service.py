from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from igab.config import settings
from igab.db.models import User
from igab.domain.exceptions import AuthenticationError
from igab.repositories.user_repo import UserRepository


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "access"},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as e:
        raise AuthenticationError("Invalid or expired token") from e


class AuthService:
    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def login(self, email: str, password: str) -> tuple[str, str]:
        user = await self.user_repo.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")
        access_token = create_access_token(str(user.id))
        refresh_token = create_refresh_token(str(user.id))
        return access_token, refresh_token

    async def refresh(self, refresh_token: str) -> str:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token")
        return create_access_token(user_id)

    async def get_current_user(self, token: str) -> User:
        import uuid

        payload = decode_token(token)
        if payload.get("type") != "access":
            raise AuthenticationError("Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token")
        user = await self.user_repo.get(uuid.UUID(user_id))
        if user is None:
            raise AuthenticationError("User not found")
        return user

    async def create_user(self, email: str, password: str, display_name: str | None = None) -> User:
        from igab.domain.exceptions import DuplicateError

        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise DuplicateError("User", "email", email)
        return await self.user_repo.create(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
        )
