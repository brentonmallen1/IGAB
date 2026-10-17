"""Transaction-scoped advisory locks keyed on a row's id.

Postgres releases an `xact` lock at COMMIT or ROLLBACK, so a holder can never
leak one past its request, and a second request asking for the same key waits
until the first has made its work visible — which is the point: the waiter
then sees what the holder did instead of redoing it.

Keyed on the first eight bytes of the UUID, as a signed bigint. Two ids
colliding in those bytes would only serialize two unrelated pieces of work.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def lock_for_transaction(session: AsyncSession, key: uuid.UUID) -> None:
    """Block until this transaction holds the lock for `key`."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(key.bytes[:8], "big", signed=True)},
    )
