# IGAB — I've Got A Budget

Self-hosted YNAB-like envelope budgeting app. Single-user, zero-based budgeting.

## Stack
- Backend: Python 3.13, FastAPI (async), SQLAlchemy + asyncpg, Alembic, uv
- Frontend: React 19 + TypeScript, Vite, Zustand, React Query, recharts, lucide-react
- DB: PostgreSQL
- Deployment: Docker Compose (nginx in production profile)

## Key Commands (justfile)
- `just dev` — docker compose watch (full stack, live reload)
- `just dev-backend` — uvicorn with reload, reads .env, connects to localhost DB
- `just dev-frontend` — Vite HMR dev server
- `just dev-migrate` — run Alembic migrations against local DB
- `just migrate` — run migrations inside Docker container
- `just migration <name>` — generate new Alembic migration
- `just lint-backend` / `just format-backend` — ruff check/format
- `just typecheck-backend` — ty type checking
- `just check-backend` — run all backend quality checks (lint + typecheck)
- `just typecheck` — frontend TypeScript type check (`tsc`)
- `just test-backend` / `just test-frontend` — run tests in Docker

## Backend Conventions
- Source root: `backend/src/igab/`; PYTHONPATH must include `src`
- Async throughout: use `async def` handlers, `await` DB calls
- Ruff: line-length 100, rules E/F/I/UP
- pytest-asyncio with `asyncio_mode = "auto"`
- `unset CORS_ORIGINS` before sourcing .env locally — bash mangles JSON arrays

## Frontend Conventions
- Per-component CSS files (`ComponentName.css`) — no global styling
- State: Zustand stores in `src/stores/`
- API calls: React Query + axios via `src/api/`
- Charts: recharts; icons: lucide-react

## Environment
- Copy `.env.example` → `.env`; configure DB, JWT `SECRET_KEY`, ports
- `VITE_API_URL` points frontend at backend API

## Code Quality
- Before finishing any backend change: run `just quality` (ruff fix + format + ty)
- Before finishing any frontend change: run `just typecheck` (tsc)
- Fix all type errors and lint violations — do not leave warnings

## Testing Requirements
- Any code touching amount calculations, budget distribution, category assignment, or transaction reconciliation requires exhaustive test coverage — this is the core trust surface of the app
- Cover edge cases: zero balances, negative amounts, overspending, partial allocation, rounding

## Library Preferences
- Prefer established libraries over custom implementations; only go custom if the overhead clearly outweighs the benefit
- Existing choices: recharts (charts), lucide-react (icons), React Query (async state), Zustand (client state), axios (HTTP)
