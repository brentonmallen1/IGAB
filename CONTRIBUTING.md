# Contributing / Development Guide

This document is the map for doing development work on IGAB — including
"future you" coming back after months away. It covers environment setup, repo
layout, conventions, quality gates, and the rules that are non-negotiable
(money math and theming).

## Prerequisites

- **Docker** with Compose (the whole stack runs in containers)
- **[just](https://github.com/casey/just)** — command runner; `just` with no
  arguments lists every recipe
- **[uv](https://docs.astral.sh/uv/)** — Python dependency management (backend)
- **Node.js** + npm (frontend dev server outside Docker)
- Python 3.13 (managed by uv)

## Getting Set Up

```sh
just init          # copy .env.example → .env, then edit it
just dev           # full stack via docker compose watch (live reload)
just migrate       # run Alembic migrations inside the container
```

For faster iteration you can run pieces natively against the containerized DB:

```sh
just dev-db        # start only PostgreSQL
just dev-backend   # uvicorn --reload on :8000, reads .env, connects to localhost DB
just dev-frontend  # Vite dev server with HMR
just dev-migrate   # Alembic against the local DB
```

Gotchas:

- The backend source root is `backend/src/igab/`; `PYTHONPATH` must include
  `src` (the just recipes handle this).
- `unset CORS_ORIGINS` before sourcing `.env` in a shell — bash mangles JSON
  arrays, so pydantic-settings must read it from `.env` directly (again, the
  just recipes handle this).

## Repo Layout

```
backend/
  src/igab/
    api/v1/          # FastAPI routers (one module per feature area)
    services/        # business logic (budget math lives here)
    repositories/    # data access
    db/models.py     # SQLAlchemy models
  alembic/versions/  # migrations (currently a single squashed 0001)
  tests/
    unit/            # service-level tests
    integration/     # API tests + factories
frontend/
  src/
    pages/           # route-level pages
    components/      # feature components, one folder per component
    stores/          # Zustand stores
    api/             # React Query + axios API layer
    themes/          # theme definitions (CSS custom properties)
docker-compose.yml   # dev stack + production profile (nginx, db-backup)
justfile             # all commands — run `just` to list them
CHECKLIST.md         # living roadmap / phase tracker
CLAUDE.md            # AI-assistant guide (kept in sync with this file)
```

## Quality Gates

Nothing merges (or gets committed, realistically) without passing:

| Scope | Command | What it runs |
| --- | --- | --- |
| Backend | `just quality` | ruff --fix, ruff format, ty type check |
| Backend | `just check-backend` | lint + typecheck (no auto-fix) |
| Frontend | `just typecheck` | `tsc` |
| Tests | `just test-backend` / `just test-frontend` | pytest / vitest in Docker |

Fix **all** lint violations and type errors — don't leave warnings behind.

## Backend Conventions

- **Async throughout**: `async def` handlers, `await` every DB call.
- Ruff config: line length 100, rules `E/F/I/UP`.
- pytest-asyncio runs with `asyncio_mode = "auto"` — no decorators needed.
- Follow the existing layering: router → service → repository. Budget math
  belongs in services, not in routers.
- Migrations: `just migration <name>` generates an autogenerate revision;
  review it before committing (autogenerate misses things like server
  defaults and enum changes).

## Frontend Conventions

- **Per-component CSS files** (`ComponentName.css`) — no global styling.
- Client state: Zustand stores in `src/stores/`. Server state: React Query
  via the `src/api/` layer (axios). Don't mix the two.
- Charts: recharts. Icons: lucide-react.
- Prefer established libraries over custom implementations; only go custom
  when the dependency overhead clearly outweighs the benefit.

### Theming — non-negotiable

The app ships 9 themes (dark, light, Gruvbox dark/light, Catppuccin
Mocha/Latte, Rosé Pine + Moon, Nord), and every one must work with every
change:

- **Never hard-code colors.** Use CSS custom properties
  (`var(--color-accent)`, `var(--bg-primary)`, …) so all themes benefit.
- Honor each theme's source material — Nord is icy, Gruvbox is warm earth,
  Catppuccin is modern purple. Don't fight the palette.
- Color is reserved for meaningful state (overspent, funded, warning), not
  decoration. Calm by default.
- Best-effort WCAG AA: contrast, keyboard navigation, visible focus.

Established UI patterns (like the floating selection bar for multi-select
bulk actions) are documented in `CLAUDE.md` — reuse them rather than
inventing parallel ones.

## Testing Requirements

**Money math is the trust surface of this app.** Any code touching amount
calculations, budget distribution, category assignment, or transaction
reconciliation requires exhaustive test coverage — no exceptions. Cover:

- zero balances and empty months
- negative amounts and refunds
- overspending and carryover behavior
- partial allocation
- rounding (everything is integer cents; if you find yourself with a float
  in money code, stop)

The backend suite lives in `backend/tests/` (unit + integration, with
factories in `tests/integration/factories.py`). Run the invariant-style
integration tests after touching sync, import, or reconciliation code — and
run the in-app Data Integrity check against a realistic database before
trusting a change to budget math.

## Workflow

1. Check `CHECKLIST.md` first — it's the living roadmap and records what's
   done, in progress, and deliberately deferred. Update it as you go.
2. Branch from `main`, keep commits focused, and make the message describe
   the user-visible change.
3. Run the quality gates for whatever you touched (see table above) plus the
   relevant test suite before committing.
4. If you change conventions or add a pattern others should reuse, document
   it in `CLAUDE.md` (AI assistant guide) and here if it affects humans.

## Picking Work Back Up After a Break

- `git log --oneline -15` and `CHECKLIST.md` will tell you where things
  stand faster than anything else.
- Verify the stack still comes up clean: `just dev`, `just migrate`, log in,
  run Settings → Data Integrity.
- Restore a recent backup into a scratch database before doing anything
  invasive — `just restore <file>` is destructive by design.
