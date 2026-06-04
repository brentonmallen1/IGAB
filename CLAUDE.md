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

## Design Context

### Users
Small household (1–2 people). Primary user is technically savvy; a second user (partner/family member) may be less technical. Core job: track spending, manage envelope budgets, feel in control of household finances. Used regularly — daily or weekly.

### Brand Personality
**Three words: Steady. Clear. Trustworthy.**

Financial data is stressful. IGAB should feel like a reliable tool — not a product trying to impress. Confidence comes from clarity, not visual flourish.

### Aesthetic Direction
**Refined functional** — beautiful because it works, not because it decorates.

- **Multi-theme is a core feature**: The app ships 7 themes (dark, light, gruvbox dark/light, catppuccin mocha/latte, rosé pine, rosé pine moon, nord). Any design work must preserve and honor all themes — changes to components must use CSS custom properties so all themes benefit. Do NOT hard-code colors.
- Each theme has its own personality (Catppuccin = modern purple, Nord = icy blues, Gruvbox = warm earth tones, Rosé Pine = dusty rose/purple) — honor the source material, don't fight it.
- Muted, purposeful color — accent reserved for meaningful state, not decoration
- Information density is a feature, not a problem to design away
- Typography is currently system fonts — could be elevated to signal more care

**Anti-references**: No flashy fintech (gradient text, glowing numbers, neon-on-dark). No generic SaaS (card grids, hero metrics, Inter + rounded corners). No corporate/enterprise (gray Excel lookalike).

### UI Patterns

#### Floating Selection Bar
Used when the user has selected multiple items and bulk actions are available. First introduced on the Payees page; use this pattern for any future multi-select context.

- **Position**: Fixed, horizontally centered, `bottom: calc(var(--spacing-lg) * 2)` — higher than the page edge so it reads clearly
- **Background**: `var(--color-accent)` — solid accent color so it pops against page content
- **Text/icons**: `var(--bg-primary)` — inverted from the accent for contrast
- **Buttons inside**: `rgba(0, 0, 0, 0.15)` background, darken on hover — layered on the accent
- **Divider**: `rgba(0, 0, 0, 0.2)` — subtle on the accent background
- **Close button**: opacity 0.7, full opacity on hover

### Design Principles
1. **Meaning over decoration** — every visual element earns its place by carrying information or guiding attention
2. **Calm by default** — restrained palette, color reserved for genuine state changes (overspent, funded, warning)
3. **Theme integrity** — all 7 themes must work; use CSS custom properties throughout, never hard-code colors
4. **Trust through consistency** — interactions behave predictably, patterns are uniform throughout
5. **Accessible without fuss** — best-effort WCAG AA: proper contrast, keyboard nav, clear focus indicators
