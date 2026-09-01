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
- `just check-pii` — refuse to ship personal data; runs first in `just ci`
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

## One Implementation Each — Not Negotiable

**A rule with two implementations is a bug that has not surfaced yet.** Not a
smell, not tech debt to schedule: a defect with a delay fuse. Every duplicate
in this repo's history has drifted, without exception, and each one was
plausible when it was written.

The receipts:

- "Needs a category" reached **eight** copies before it was consolidated. Two
  of them disagreed. The badge said 3 while the register drew 930, and a
  budgeting app that contradicts itself is one the user stops believing.
- Anchored-dropdown geometry reached **five** copies. Only two clamped to the
  viewport, so three ran off the right edge; only one flipped upward, so a
  combobox opened near the bottom of the register drew its list below the
  fold. Nobody decided that. It is what five people solving one problem on
  five days produces.
- TagPicker wrote its three size limits **twice** — once inline, once in CSS.
  The inline copy silently won every time, so the stylesheet's copy was free
  to say anything at all.

Note the second and third: **this rule is not about money.** Money is where
drift costs trust, which is why the boundary rule below is written in those
terms — but geometry, formatting, validation, and CSS constants rot exactly
the same way.

### When you find a duplicate

**Fix it in the change you are already making.** Not in a follow-up, not in a
TODO, not in a comment asking the next reader to keep the copies in step —
every such comment in this repo's history was attached to something that had
*already* drifted. A comment is not a mechanism.

The procedure, in order:

1. **Count the copies before you touch one.** `grep` the constant, the
   arithmetic, the predicate. You are looking for the number, not an example —
   the fifth copy is the one that tells you this is systemic.
2. **Diff them.** The differences are the bug list. Write them down; each one
   is either a defect to fix or a deliberate variation to express as a
   parameter. There is no third category.
3. **Extract to the home named in the table below** — pure logic separate from
   the wiring, so it is testable without a browser or a database.
4. **Convert every call site.** All of them. A consolidation that leaves one
   copy behind has raised the copy count by one.
5. **Test the differences from step 2 by name.** Each divergence becomes a
   test case that says which component used to get it wrong.

**If you are about to copy code, you have found a duplicate** — at the only
moment it is still free to fix. Extract first, then use it twice.

**Never widen a rule's footprint to avoid touching a caller.** Adding a
parameter that only one caller passes, or a second function beside the first
"for now", is how three copies become five.

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
| Frontend UI geometry | `frontend/src/utils/anchoredPosition.ts` + `hooks/useAnchoredPosition.ts` |
| A constant two layers both need | one of the above, never once in TS and again in CSS |

Anything in `services/` that is a *rule* rather than an *orchestration* belongs
in one of those.

**Split pure from wired.** `anchoredPosition.ts` takes the viewport as an
argument instead of reading `window`, so every branch is a one-line test; the
hook beside it does the measuring and the listeners. Logic that can only be
exercised by mounting a component will not get the tests that keep copies from
re-appearing.

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

## Never Commit Personal Data — Not Negotiable

**This repository is public.** Read that again before pasting anything from a
real budget into a test, a fixture, a docstring, or a commit message.

It has already leaked. A captured SimpleFIN response was committed verbatim:
250 real transactions on one checking account, 53 rows carrying a person's
name, 26 reference numbers — a mortgage loan number, a student loan number, a
life insurance policy number, a medical payment plan, a state tax refund line.
The account's own name carried its last four digits and its balance. It went in
under a sanitizer whose docstring promised to replace "personal names in
descriptions" and whose code had no name handling at all. No test ever loaded
the file. Removing it meant rewriting published history.

**`just check-pii` is the gate, and it runs first in `just ci`.** Prose did not
stop this the first time; a comment is not a mechanism here either.

### What counts

Anything that identifies a **person**, an **employer**, or an **account**:

- Names — yours, a partner's, anyone's. In test data, in a docstring, anywhere.
- Employers and payroll descriptors — the bank string for a direct deposit
  carries the payroll provider *and* the employee name.
- Institutions tied to *your* accounts: the bank, the card issuer, the loan
  servicer, the insurer. Merchant chains are fine — `Nordstrom` identifies
  nobody; a named mortgage servicer plus a loan number identifies a house.
- Account and reference numbers, partial account numbers, last-four digits.
- Real balances and real amounts from a live budget.

### What to do instead

Docstrings here are good *because* they cite the budget that produced the bug —
the amount, the payee, the envelope it landed in. **Keep the specificity and
make the facts fictional.**

- Use the shared invented vocabulary: `Sapphire Visa`, `Harborstone`,
  `Cascade Point HYSA`, `Northwind Payserv`, `Jane Doe`.
- Rescale amounts. A comment teaches with the *ratio*, never the digits.
  `$4,180 on a card owing $2,690` explains exactly what the real pair did.
- Never commit a captured API response you have not read end to end.
  `capture_simplefin_fixtures.py` now requires `--redact` per person, reaches
  `description`/`payee`/`memo`, and `assert_clean` refuses to write output that
  still carries a redact term or a run of 5+ digits.
- A fixture under `tests/fixtures/` that looks like a bank feed must be listed
  in `REVIEWED_FIXTURES` in `scripts/check-pii.py`. Adding the line *is* the
  review. Do not add one for a file you have not opened.
- Found a real identifier? Remove it **and add it to the deny-list**:
  `python3 scripts/check-pii.py --add "Some Name"` prints the digest to paste
  in. That list is a ratchet — the only part of the check that knows what your
  real data looks like.
- **The deny-list is hashed on purpose.** A plaintext list of strings you must
  never publish is itself a list of strings you must never publish; the first
  version of that file leaked six of them into the commit that added the check.
  Hashes also survive a history rewrite, where a `--replace-text` pass would
  otherwise leave the list denying the fictional names and passing the real
  ones.

### If something real does get committed

Assume it is public the moment it is pushed. Scrubbing the working tree does
not unpublish it: the blob stays in history, and on GitHub it also stays behind
`refs/pull/<n>/head`, which a force-push cannot reach. Removal means rewriting
history *and* asking GitHub Support to purge the stale refs — or deleting and
recreating the repository. Say so plainly rather than implying a `git commit`
fixed it.

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
    `react-hooks/rules-of-hooks` is deliberately NOT in that backlog — a
    component whose hook count changes between renders is broken, not untidy.

## Testing Requirements
- Any code touching amount calculations, budget distribution, category assignment, or transaction reconciliation requires exhaustive test coverage — this is the core trust surface of the app
- Cover edge cases: zero balances, negative amounts, overspending, partial allocation, rounding

### A card behaviour with no scenario is a behaviour nobody demoed

Card situations live once, in
`backend/src/igab/sample_budget/card_scenarios.py`: the events, and the
position the card must read once they have happened. Three suites are
parametrised over `ALL_SCENARIOS` — pure domain, served summary, generated
sample data — so **adding a scenario adds three tests and cannot be added
un-asserted**, and the generator refuses to build a card whose declared
position it does not reach.

When you change what a card's figures do, add or update a scenario. Do not
pin a card behaviour with a hand-built fixture when a scenario would say it
once, and do not give the sample budget a card that takes an inflow without
declaring what that card should then read — an inflow is what this model has
been bitten by twice.

This exists because six situations had to be hand-built twice each, in two
different vocabularies, and none of them could be *shown* to anybody: the
generator asserted that no card inflow may exist anywhere in the register,
which was true and which forbade every interesting card from the demo.

- **`expect` is written by hand, never derived.** Deriving it from the walk
  makes every assertion a tautology — the arithmetic is the thing under test.
  Keep the figures round enough to check on paper.
- **`None` in an `ExpectedPosition` means the scenario does not claim that
  figure**, and is the honest answer where texture decides it. It is not a
  synonym for zero.
- Fixtures and amounts are invented and rescaled, like everything else here —
  see the personal-data rule above.

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

### Surfaces
One vocabulary for "what a section looks like", defined once in
`src/themes/base.css` (roles and the `.surface` rules) with `components/common/Surface` as the React wiring:
`--surface-canvas` (page), `--surface-raised` (cards, sections), `--surface-sunken`
(wells inside a card — scroll boxes, table bodies), `--surface-chrome` (toolbars,
filter bars, sticky headers), `--surface-overlay` (modals, popovers), with `--edge`
(hairline) and `--edge-strong`. Page-level containers use `<Surface>` or the
`surface` class; they do not paint `--bg-*` themselves. Themes author the
four-grey ladder; `contrast.test.ts` holds every theme to the picked contract
(raised one 8-pt lightness step above the canvas, hairlines visible on it) and
`scripts/retune-surfaces.mjs` regenerates a theme's ladder to meet it.

### Design Principles
1. **Meaning over decoration** — every visual element earns its place by carrying information or guiding attention
2. **Calm by default** — restrained palette, color reserved for genuine state changes (overspent, funded, warning)
3. **Theme integrity** — all 40 theme variants must work; use CSS custom properties throughout, never hard-code colors
4. **Trust through consistency** — interactions behave predictably, patterns are uniform throughout
5. **Accessible without fuss** — best-effort WCAG AA: proper contrast, keyboard nav, clear focus indicators
