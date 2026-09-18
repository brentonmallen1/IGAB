"""Issuing and checking read-only API keys.

The app's own credentials do not fit an assistant. An access token lasts 30
minutes, which is no use to a client configured once and left alone; a refresh
token lasts 90 days and can mint access tokens with full WRITE access to
everything its owner has. Handing either to an MCP client would be handing it
the whole budget.

A key is the narrow thing: read-only, scoped to named budgets, revocable by
itself, and a plain bearer token so anything that can set a header can use it
— no per-vendor OAuth flow.

Only the hash is stored, so a key is shown once and never again.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from igab.db.models import ApiKey, ApiKeyBudget

#: Marks a key as ours at a glance — in a config file, a log, a support
#: question. Also what lets the JWT path reject one with a useful message
#: instead of "invalid token".
KEY_PREFIX = "igab_"

#: Characters of the key kept in the clear, the marker included. Enough to
#: tell two keys apart in a list, far too few to reconstruct one.
PREFIX_LENGTH = 12

#: 32 bytes of URL-safe randomness. Brute force is not the threat model at
#: this size; leakage is, which is what revocation is for.
_SECRET_BYTES = 32


@dataclass(frozen=True)
class ApiKeyPrincipal:
    """Who a verified key speaks for, and what it may read."""

    key_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    budget_ids: tuple[uuid.UUID, ...]

    def may_read(self, budget_id: uuid.UUID) -> bool:
        return budget_id in self.budget_ids


def generate() -> tuple[str, str, str]:
    """(the key itself, its prefix, its hash).

    The caller stores the second two and shows the first once. Returning all
    three from one function is what stops a call site hashing it differently.
    """
    raw = f"{KEY_PREFIX}{secrets.token_urlsafe(_SECRET_BYTES)}"
    return raw, raw[:PREFIX_LENGTH], hash_key(raw)


def hash_key(raw: str) -> str:
    """SHA-256, hex.

    Not bcrypt. bcrypt is deliberately slow to make guessing a low-entropy
    password expensive; this is 256 bits of randomness, so there is nothing
    to guess, and it is checked on every single request.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


def looks_like_api_key(token: str) -> bool:
    """Whether this bearer is one of ours.

    Used by BOTH doors to refuse the other's credential with a message that
    says what went wrong: the REST API tells you an API key belongs on the
    MCP endpoint, and the MCP endpoint tells you a session token is not a key.
    "Invalid token" for either is the kind of answer that costs an evening.
    """
    return token.startswith(KEY_PREFIX)


async def authenticate(session: AsyncSession, raw: str) -> ApiKeyPrincipal | None:
    """The principal behind a key, or None.

    None covers every failure on purpose — unknown, revoked, malformed. A
    caller that could tell them apart would be an oracle for which keys exist.
    """
    if not looks_like_api_key(raw):
        return None
    result = await session.execute(
        select(ApiKey)
        .where(ApiKey.key_hash == hash_key(raw), ApiKey.revoked_at.is_(None))
        .options(selectinload(ApiKey.budgets))
    )
    key = result.scalar_one_or_none()
    if key is None:
        return None
    # Best-effort: a failed stamp must never fail the request it describes.
    # The column answers "is this key still in use", not "how many calls".
    key.last_used_at = datetime.now(tz=UTC)
    return ApiKeyPrincipal(
        key_id=key.id,
        user_id=key.user_id,
        name=key.name,
        budget_ids=tuple(link.budget_id for link in key.budgets),
    )


async def create_key(
    session: AsyncSession, *, user_id: uuid.UUID, name: str, budget_ids: list[uuid.UUID]
) -> tuple[ApiKey, str]:
    """A new key and the one chance to read it.

    The caller must already have checked that this user may reach each budget
    — the key cannot grant more than its maker has.
    """
    raw, prefix, hashed = generate()
    key = ApiKey(user_id=user_id, name=name, key_hash=hashed, prefix=prefix, scopes="read")
    session.add(key)
    await session.flush()
    for budget_id in dict.fromkeys(budget_ids):
        session.add(ApiKeyBudget(api_key_id=key.id, budget_id=budget_id))
    await session.flush()
    return key, raw


async def revoke(session: AsyncSession, key: ApiKey) -> None:
    """Stamped, not deleted, so a key seen in a log can still be identified."""
    key.revoked_at = datetime.now(tz=UTC)
    await session.flush()
