"""Integration test fixtures: real PostgreSQL, per-xdist-worker databases.

Design constraints:
- pyproject sets `-n auto` (pytest-xdist), so each worker gets its own database
  named igab_test_{worker_id} to avoid cross-worker interference.
- pytest-asyncio uses a fresh event loop per test, so the async engine/session
  must be function-scoped (an async engine cannot hop loops). Database and
  schema creation happen once per worker via a session-scoped *sync* fixture
  (psycopg2 is already a project dependency).
- Each test runs inside an outer transaction that is rolled back at teardown.
  `join_transaction_mode="create_savepoint"` turns any commit() issued by
  code under test into a savepoint release, keeping the outer rollback intact.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from igab.db.models import Base

# In-container, docker compose sets DATABASE_URL (host "db"). Locally, fall back
# to the same credentials on localhost (matching the `just dev-backend` recipe).
_BASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://igab:changeme@localhost:5432/igab")


def _db_name() -> str:
    return f"igab_test_{os.environ.get('PYTEST_XDIST_WORKER', 'gw0')}"


def _url(database: str, *, sync: bool = False) -> str:
    url = make_url(_BASE_URL).set(database=database)
    if sync:
        url = url.set(drivername="postgresql+psycopg2")
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def test_db() -> str:
    """Create this worker's test database with the current model schema."""
    admin = create_engine(_url("postgres", sync=True), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{_db_name()}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{_db_name()}"'))
    admin.dispose()

    schema_engine = create_engine(_url(_db_name(), sync=True))
    with schema_engine.connect() as conn:
        # `import_anchors` carries an EXCLUDE ... USING gist constraint, whose
        # `<>` operator comes from btree_gist. The migration creates the
        # extension; this fixture builds the schema from the models instead, so
        # it has to create it too or `create_all` fails on that table.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        conn.commit()
    Base.metadata.create_all(schema_engine)
    schema_engine.dispose()
    return _db_name()


@pytest.fixture
async def api_client(db_session):
    """httpx client against the real app with session/auth overridden."""
    from httpx import ASGITransport, AsyncClient

    from igab.db.session import get_session
    from igab.dependencies import get_current_user
    from igab.main import app

    from .factories import create_user

    # Admin, mirroring the env-bootstrapped primary user — settings writes and
    # backup endpoints are admin-gated. Authz tests create explicit non-admin
    # users when they need the other side.
    user = await create_user(db_session, is_admin=True)

    async def _session_override():
        yield db_session
        # Production get_session commits at request end; the session here runs
        # autoflush=False, so flush to make each request's writes (including
        # change-log rows added without an explicit flush) visible to the next.
        await db_session.flush()

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.test_user = user  # type: ignore[attr-defined]
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def db_session(test_db: str):
    """Function-scoped session wrapped in an always-rolled-back transaction."""
    engine = create_async_engine(_url(test_db), poolclass=NullPool)
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if outer.is_active:
                await outer.rollback()
    await engine.dispose()
