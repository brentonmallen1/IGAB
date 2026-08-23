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

## Money Rules: One Implementation Each

A money rule with two implementations will drift. It has, repeatedly — "needs a
category" reached eight copies before it was consolidated, and the copies
disagreed twice. Duplication becomes deviation, and deviation in a budgeting
app becomes distrust: the badge says 3, the register draws 930, and the user
stops believing any of the numbers.

**The boundary rule.** Before writing a rule, decide where it lives:

> A rule belongs on the **server** iff the server also decides it, or the client
> is missing an input. A rule belongs in **one client module** iff it is pure
> presentational composition of server-supplied facts, and the server never
> decides it.

`is_assignable` is a server field because the server assigns money. Which group
headers to render stays on the client because the server never renders headers.
**If you add a server field no backend path reads, you have crossed back.**

Two traps this rule catches, both of which produced real bugs:

- *"The client already has the fields."* Check. `CategoryResponse` did not
  expose `linked_liability_id`, and `CategoryRepository.get_all` filters the
  category's `is_hidden` but not the group's — so the client could not have
  computed the answer it was computing.
- *"I'll mirror it and keep the two in sync with a comment."* Every mirror in
  this repo that carried such a comment had already drifted when it was found.
  A comment is not a mechanism.

**One home per rule kind:**

| Kind | Home |
|---|---|
| SQL predicates over transactions | `backend/.../repositories/txn_filters.py` |
| SQL predicates over categories | `backend/.../repositories/category_filters.py` |
| Pure money/date functions | `backend/.../domain/` (`money`, `splits`, `carryover`, `dates`, `matching`) |
| Frontend, cross-feature | `frontend/src/utils/` |
| Frontend, feature-local | a colocated pure module (`reviewSection.ts`, `budgetTotals.ts`) |

Anything in `services/` that is a *rule* rather than an *orchestration* belongs
in one of those.

**Serving a computed field** — the pattern, from `needs_category`:

1. One expression constant in the relevant `*_filters.py`.
2. `query_expression()` on the model, with a comment saying why it cannot be a
   column.
3. A `with_*` loader on the repository as the only way to populate it, plus
   `get`/`refresh`/`create` overrides so mutations do not drop it.
   `populate_existing=True` is load-bearing. Check `get_with_tags`-style
   variants too — those are what the create/update endpoints serialize from.
4. **Required, not optional**, on the response schema. A path that forgets must
   raise, not report unfiled work as filed.
5. Hand-add the field to `frontend/src/types/index.ts` with a comment pointing
   home, and delete the client-side rule.
6. Add it to any `memo` comparator — a served field can change with no other
   field moving.
7. Extend `tests/integration/test_offbudget_categories.py`'s checklist: every
   listing path carries it, it survives a service update, every mutating
   endpoint returns a serializable row.

**Irreducible duplication.** Some rules must exist twice — the split editor does
arithmetic while the user types, before any round-trip. Then: one
implementation per side, and a shared fixture both suites run
(`shared/split_cases.json`) or a differential test
(`tests/integration/class_agreement.py`). Never a comment asking the next
reader to keep two copies in step.

**Deliberate divergence is fine, silence is not.** Where two numbers legitimately
differ — the badge and the Uncategorized filter on `POSTED`, the header and
reconcile on future-dated rows — say so at the definition, bound it, and pin it
with a test that fails if the gap widens.

**Money parsing.** `parseAmountInput` for anything a person typed;
`parseApiDecimal` for a canonical server string. Never bare `parseFloat` — eslint
enforces this. Never `|| 0` on a parsed amount: unparseable input must surface an
error, never silently book zero.

## Code Quality
- Before finishing any backend change: run `just quality` (ruff fix + format + ty)
- Before finishing any frontend change: run `just typecheck` (tsc)
- Fix all type errors and lint violations — do not leave warnings
- **`just ci` runs exactly what GitHub CI runs, locally and without Docker.**
  Use it before pushing. The other recipes shell into docker compose, and when
  the containers aren't up it is tempting to substitute an equivalent — but:
  - `npx tsc --noEmit` **checks nothing** and exits 0. The root `tsconfig.json`
    is `{"files": [], "references": [...]}`, so with no file arguments it
    compiles an empty program. The real check is `tsc -b` (`npm run typecheck`).
  - CI runs `ruff format --check src/`, which `just check-backend` includes but
    a bare `ruff check` does not. `just quality` formats for you.
  - `npm run lint` is a real gate now (it was `continue-on-error` against a red
    baseline). The legacy react-hooks/react-refresh backlog is `warn`; the
    warning count is the debt and should go down, never up.

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

- **Multi-theme is a core feature**: The app ships 20 palettes in 40 dark/light variants (see `PALETTES` in `src/stores/appStore.ts`). Any design work must preserve and honor all of them — changes to components must use CSS custom properties so every theme benefits. Do NOT hard-code colors.
- **Contrast is enforced, not assumed**: `src/themes/contrast.test.ts` holds every palette to WCAG AA (4.5:1 for text, 3:1 for input borders) across all its surfaces. A new theme is not done until that suite passes. Most UI text renders at 10–13px, so the large-text exemption never applies.
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
3. **Theme integrity** — all 40 theme variants must work; use CSS custom properties throughout, never hard-code colors
4. **Trust through consistency** — interactions behave predictably, patterns are uniform throughout
5. **Accessible without fuss** — best-effort WCAG AA: proper contrast, keyboard nav, clear focus indicators
