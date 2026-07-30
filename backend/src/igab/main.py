from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from igab.api.v1.router import api_router
from igab.config import settings
from igab.db.session import engine, init_db
from igab.domain.exceptions import IGABError, NotFoundError
from igab.tasks.scheduler import start_scheduler, stop_scheduler

# Known-insecure sentinel values shipped in config.py defaults and .env.example.
# Booting with any of these means the operator never configured security, so an
# attacker who reads the public source could forge tokens or log in as admin.
_INSECURE_SECRET_KEYS = frozenset(
    {"dev-secret-change-in-production", "changeme-generate-with-openssl-rand-hex-32"}
)
_INSECURE_ADMIN_PASSWORDS = frozenset({"changeme"})


def _validate_security_config() -> None:
    """Refuse to boot with default/insecure security settings.

    HS256 JWTs are signed with SECRET_KEY, so a public default key lets anyone
    forge a valid token for any user. A default admin password is a published
    credential. Fail fast rather than serve with either.
    """
    key = settings.SECRET_KEY
    if not key or key in _INSECURE_SECRET_KEYS or len(key) < 32:
        raise RuntimeError(
            "SECRET_KEY is unset, still a shipped example value, or shorter than "
            "32 characters. Set a strong random SECRET_KEY "
            "(e.g. `openssl rand -hex 32`) before starting IGAB."
        )
    if not settings.ADMIN_PASSWORD or settings.ADMIN_PASSWORD in _INSECURE_ADMIN_PASSWORDS:
        raise RuntimeError(
            "ADMIN_PASSWORD is unset or still a shipped example value. Set a "
            "strong ADMIN_PASSWORD before starting IGAB."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_security_config()
    await init_db()
    await _bootstrap_admin()
    await _seed_settings()
    start_scheduler()
    yield
    stop_scheduler()
    await engine.dispose()


async def _seed_settings() -> None:
    from igab.db.session import AsyncSessionLocal
    from igab.repositories.settings_repo import SettingsRepository
    from igab.services.settings_service import SettingsService

    async with AsyncSessionLocal() as session:
        try:
            svc = SettingsService(SettingsRepository(session))
            await svc.seed_from_env()
            await session.commit()
        except Exception:
            await session.rollback()


async def _bootstrap_admin() -> None:
    """Create the admin user if it doesn't exist yet."""
    from igab.db.session import AsyncSessionLocal
    from igab.repositories.user_repo import UserRepository
    from igab.services.auth_service import AuthService

    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        auth = AuthService(repo)
        existing = await repo.get_by_email(settings.ADMIN_EMAIL)
        if existing is None:
            try:
                await auth.create_user(
                    email=settings.ADMIN_EMAIL,
                    password=settings.ADMIN_PASSWORD,
                    display_name="Admin",
                )
                await session.commit()
            except Exception:
                await session.rollback()


app = FastAPI(
    title="IGAB API",
    description="I've Got A Budget — self-hosted envelope budgeting",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(IGABError)
async def igab_error_handler(request: Request, exc: IGABError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Catch-all so unhandled DB/runtime errors return a proper 500 WITH CORS headers.
    # Without this, ServerErrorMiddleware sends the 500 outside the CORS wrapper.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
