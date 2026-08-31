from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from igab.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """The request-scoped session.

    **The commit below is not what makes a request durable.** FastAPI closes
    `yield` dependencies after the response has been sent, so by the time this
    line runs the client has already been told the write landed and may
    already have refetched it — off a different pooled connection, from a
    snapshot that predates the commit. `igab.api.route.CommitRoute` does the
    real commit, inside the handler, before the send. It finds the session on
    `request.state`, which is the only reason this takes a request; the commit
    here is left as the harmless no-op it becomes once nothing is dirty.

    The `except` is the point of the exit code: a failed request must leave
    nothing open, and a teardown is exactly the right place to guarantee that.
    Making a change durable is not — see `CommitRoute`'s module docstring for
    why, in FastAPI's own source.
    """
    async with AsyncSessionLocal() as session:
        request.state.session = session
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    from igab.db.models import Base  # noqa: F401 — ensure models are registered

    async with engine.begin():
        # Tables are managed by Alembic; this is a safety check only
        pass
