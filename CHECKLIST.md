# IGAB Feature Checklist

Track implementation progress here. Add new items to Backlog as they come up.

_Reconciled 2026-07-21 after the financial-correctness audit (commit 540c2ac)._

---

## Cutover blockers (do before/while replacing YNAB)

- [x] YNAB import: account-type mapping step (preview endpoint + Review Accounts step on the budget selector with name-based type suggestions)
- [x] Code backup: pushed to private remote github.com/brentonmallen1/IGAB
- [ ] CI: run `just quality` + backend suite (needs Postgres service) + `npm run typecheck` on push, or at minimum a `just ci` recipe run before commits
- [ ] Execute cutover per README.md (fresh DB → import → double sync → integrity green → parallel-run one statement cycle)

---

## Phase 2: In Progress

### Reports — Remaining / Polish
- [ ] Drill-down tables (click chart element → filtered transaction list)
- [ ] Export per report (CSV / JSON / PNG) — transaction export exists; per-report export does not
- [ ] Multi-select searchable dropdowns for category / payee / account filters
- [ ] Spending treemap — needs fix (broken drill-down)
- [ ] Sankey — comparison with other time windows

---

## Phase 3: Polish & PWA

### Advanced Accounts
- [ ] Loan accounts with amortization schedule
- [ ] Interest calculation
- [ ] Extra payment simulation

### PWA
- [ ] App manifest (installable)
- [ ] Service worker
- [ ] IndexedDB offline cache
- [ ] Sync queue for offline mutations
- [ ] Conflict resolution strategy

### Mobile UX
- [ ] Geofencing for payee suggestions — sort/suggest payees by proximity when on mobile (requires location permission, opt-in via settings)

---

## Phase 4: Planning
- [ ] What-if scenarios
- [ ] Loan calculators

---

## Backlog

_Add items here as they come up during development._

### Budget page money movement (YNAB-parity cluster)
- [x] Move money to/from a category (API endpoint + click-the-available popover, TBA both directions, budget_moves history table + per-month endpoint)
- [ ] Auto distribute ready-to-assign funds to cover overspent categories
- [ ] Total overspent display
- [ ] TBA money up and center (YNAB-style hero) with drawer: auto-fund overspent + total overspend amount
- [ ] Move-history view beyond the popover (full month log)

### UI / UX
- [ ] Entire polish pass — home page budget list, hero-like TBA section, more modern/thoughtful layout
- [ ] Command palette (add transaction, search/filter, budget actions, switch views)
- [ ] Custom reminder notifications (pay bills, etc.)
- [ ] Explicit "set as default category" affordance on payees (memory now learns once and never overwrites; changing the default is only possible via the payee edit form)

### Payees
- [ ] Auto-suggest merges via rapidfuzz — merge wizard with final review before commit
- [ ] Payee list: sort, filter/search, column alignment

### Transactions
- [ ] Split transaction button always accessible (outside scroll area), opens modal
- [ ] Split transaction "add remaining to category" button

### Data
- [ ] Auto backups configurable in UI (daily backup container + retention exist via env vars; frequency/count/age settings do not)
- [ ] YNAB-compatible export (exit strategy — a system of record needs a way out too)
- [ ] Attachment file GC (files of long-deleted transactions are never removed from disk)

### Accounts & Finance Tools
- [ ] Savings tools section (personal finance flowchart, savings guidance)
- [ ] Education section (personal finance flowchart, other resources)
- [ ] Migrating to a new budget plan (preserve transaction history)
- [ ] Monthly category balance snapshots (O(1) budget summary, invalidate on change) — summary currently recomputes month-by-month per category; fine today, will crawl after years of data
- [ ] Budget lookback / month comparison (side-by-side via snapshots)

### Testing
- [ ] Frontend tests for money-critical components (transaction editor, split editor cents math, bulk flows) — backend has 546 tests incl. real-DB integration; frontend has only searchParser tests

### Localization
- [ ] Settings for currency, decimal vs comma separator, date format (CSV import now handles EU separators exactly; UI display settings remain)
- [ ] All numbers rounded to 2 decimal places throughout app

### Future Reports (deferred)
- [ ] Subscription tracker (detect recurring payments, show renewal cadence)
  - might be helpful to have tags functionality to be able to label a budget item as a subscription
- [ ] Debt payoff curves (principal vs interest) — needs loan amortization in CategoryTarget
- [ ] Anomaly detection with z-scores (flag outliers vs category baseline)
- [ ] Lag correlation analysis (income events → spending spikes)
- [ ] Inflation-adjusted spending trends — needs external inflation data
- [ ] "If invested instead" opportunity cost tracker — needs market proxy data
- [ ] Forward cash projection fan chart (deterministic + stochastic bands)

### Other
- [ ] 2FA (TOTP) support
- [ ] Budget notes / annotations
- [ ] Transaction flags / colors
- [ ] Multi-currency support
- [ ] Plugin framework + plugin management page
- [ ] Mock SimpleFIN API for dev (a FakeClient exists in the integration tests; a dev-mode mock server with generated timestamps does not)

---

## Completed

### Financial Correctness Audit (2026-07-21, commit 540c2ac)
- [x] Real-Postgres integration test suite (546 backend tests, money-conservation invariant checker, hand-computed dollar assertions)
- [x] Split transactions flow into category activity, budget available, and all reports (leaf-row aggregation rules in `txn_filters.py`)
- [x] Pending transactions excluded from every money aggregate (TBA never skews on bank auths)
- [x] Sync dedup: accepted matches keep sync_id (no re-import loop); pending→posted adopts bank amount/date with `entered_date` provenance; unique DB dedup indexes; stale-pending sweep
- [x] Invariant guards: transfer pairs as a unit, split integrity, reconciled lifecycle (finish auto-adjustment + unreconcile endpoint/UI), merge amount-equality + attachment reassignment
- [x] Bulk endpoints report per-item failures (frontend toasts)
- [x] Scheduled transfers create both legs
- [x] YNAB import fully idempotent including transfers, per-leg cleared preserved
- [x] Exact string→Decimal CSV parsing; NaN/scale/bounds Money validation on all amount inputs; UTC clock
- [x] Ownership scoping on all ~100 API endpoints (two-user 404 tests)
- [x] Categorized transfers to off-budget accounts count as spending (YNAB semantics)
- [x] Live integrity check (Settings → Data Integrity + `GET /budgets/{id}/integrity`)
- [x] Backups: `just backup` / `just restore` (restore exercised), daily backup container in production profile
- [x] Frontend: cents-integer money math, split-editor duplication bug fixed, typecheck restored and clean

### Reconciliation (completed during audit)
- [x] Statement matching workflow
- [x] Lock reconciled transactions (+ explicit unreconcile)
- [x] Adjustment transaction (auto-created on statement mismatch)
- [x] Reconciliation history

### Integrations (completed during audit hardening)
- [x] SimpleFIN connection setup (beta-bridge.simplefin.org)
- [x] SimpleFIN account linking
- [x] SimpleFIN transaction sync (rate-limit aware: 12 req/day, 90-day first-sync window)
- [x] Deduplication for imported transactions (sync_id exact + fuzzy auto/review matching, cross-source)
- [x] Reports test coverage (integration tests for spending, income/expense, budget-vs-actual, sankey, dashboard)
- [x] Payee management page (view, edit, merge, bulk operations)
- [x] Multi-select merge with name selection and sanity check (transaction count preview)
- [x] Backups and exports (pg_dump backups; CSV/JSON transaction export)

### Phase 1: MVP

#### Infrastructure
- [x] Docker Compose setup (api, db, frontend)
- [x] PostgreSQL schema via Alembic migrations
- [x] Environment configuration (.env)
- [x] justfile commands (dev, build, migrate, test)
- [x] JWT authentication (single user)

#### Backend — Core CRUD
- [x] Budget CRUD
- [x] Account CRUD (checking, savings, credit card, loan, tracking)
- [x] Category group CRUD
- [x] Category CRUD
- [x] Payee CRUD

#### Backend — Transactions
- [x] Transaction create / read / update / delete
- [x] Transfer handling (paired transactions, no category)
- [x] Split transactions
- [x] Transaction search & filtering
- [x] Payee auto-categorization memory

#### Backend — Budgeting Engine
- [x] Category balance calculation (prior + assigned − activity)
- [x] To Be Assigned calculation
- [x] Monthly budget assignment
- [x] Overspending handling (visual warnings: overspent row highlight + budget banner)
- [x] Auto-assign rules (fill targets, proportional by underfunded % with preview)

#### Backend — Imports
- [x] CSV import (manual / bank export)
- [x] YNAB4 importer (.yfull file)

#### Frontend — Core
- [x] Dark mode default (+ light theme toggle)
- [x] All theme palettes built (gruvbox, catppuccin, rose-pine, nord)
- [x] App layout: sidebar, header, main content
- [x] Collapsible sidebar (icon-only mode when collapsed)
- [x] Account sidebar list
- [x] Budget view (category groups + category rows)
- [x] Inline category assignment editing
- [x] Account register (transaction list)
- [x] Transaction editor (create/edit form)
- [x] Transfer entry
- [x] Split transaction entry
- [x] YNAB4 import page
- [x] CSV import page
- [x] Settings page (theme selector, account creation, budget creation)
- [x] Light/dark mode and color palette accessible at all times (header)
- [x] Uncategorized transactions — "Needs Category" warning pill
- [x] Transaction duplication (single row and bulk selection)

### Phase 2: Advanced Features

#### Goals & Targets
- [x] Needed-for-spending target
- [x] Savings balance target
- [x] Monthly funding target
- [x] Target status display (underfunded / funded)
- [x] Progress bar for funding status (expanded pill bar with %, amount remaining, monthly pace)
- [x] Monthly needed amount display for date-based savings goals
- [x] LED dot indicator in compressed row mode
- [x] Expired target detection (past target_date shows "expired" badge)
- [x] Past Targets section in inspector sidebar (view, edit to reuse, delete)

#### Scheduled Transactions
- [x] Recurring transaction rules (daily/weekly/monthly/yearly)
- [x] Auto-create vs reminder mode
- [x] Upcoming transaction projection (shown in account register)
- [x] Make repeating from transaction context menu
- [x] Payee column in scheduled transactions list

#### Themes
- [x] Gruvbox (dark + light)
- [x] Catppuccin (Mocha + Latte)
- [x] Rose Pine (+ Moon)
- [x] Nord

#### Reports — Completed
- [x] Report infrastructure: tabbed navigation (Overview, Financial State, Cash Flow, Budget, Spending, Insights)
- [x] Shared filter bar with date range presets (This Month, Last Month, Last 3/6/12 Months, Last Year, Custom)
- [x] Global group-by filter (Group / Category) applied across Pareto, Treemap, Sankey
- [x] Info (i) button on each report with explanatory modal
- [x] Overview dashboard (TBA, net worth, burn rate, savings rate, days-to-zero, income/expenses this month, top categories)
- [x] Net worth over time (stacked area by account type)
- [x] Account composition chart (checking / savings / credit card / loan / tracking over time)
- [x] Income vs expenses (bars + net cash flow line)
- [x] Rolling 30/90 day burn rate
- [x] Cash flow Sankey — drill-down: Income → Groups → Categories → Payees; Spent/Budgeted toggle
- [x] Budget vs actual (horizontal bars, sort by overspent, tooltip shows group)
- [x] Cumulative variance (running budget drift line chart)
- [x] Category volatility (std dev bars with min/max)
- [x] Pareto analysis (sorted bars + cumulative % line, grouped by group/category)
- [x] Spending treemap (hierarchical, group/category mode)
- [x] Seasonality heatmap (months × categories)
- [x] Payee analysis (top payees with % of total, recurring detection, monthly trend)
- [x] Day-of-week spending patterns
- [x] Event timeline / large transactions (annotated, limit toggle)
- [x] Transaction export (CSV / JSON) from reports page



ideas:
- create a mock api for dev instead of calling the simplefin api, it calls this and returns a static set of data. though it would have to be generated for a relevant time stamp or something?


- receipt extraction into categories and then do a split transaction. need to figure out a way to decode some things, maybe need a upc database interactoin or something to try to decode things and figure out what the item was. maybe have a table per receipt that has a column for the original item string and then the upc actual object name
