# IGAB Feature Checklist

Track implementation progress here. Add new items to Backlog as they come up.

---

## Phase 2: In Progress

### Reports — Remaining / Polish
- [ ] Drill-down tables (click chart element → filtered transaction list)
- [ ] Export per report (CSV / JSON / PNG)
- [ ] Multi-select searchable dropdowns for category / payee / account filters
- [ ] Spending treemap — needs fix (broken drill-down)
- [ ] Reports test coverage
- [ ] Sankey — comparison with other time windows

### Integrations
- [ ] SimpleFIN connection setup (beta-bridge.simplefin.org)
- [ ] SimpleFIN account linking
- [ ] SimpleFIN transaction sync (with rate-limit awareness: 24 req/day, 90-day window)
- [ ] Deduplication for imported transactions

---

## Phase 3: Polish & PWA

### Reconciliation
- [ ] Statement matching workflow
- [ ] Lock reconciled transactions
- [ ] Adjustment transaction
- [ ] Reconciliation history

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

### UI / UX
- [ ] I like in YNAB how the TBA money is up and center and it has a button to open a drawer showing auto fund overspent with total overspend amount
- [ ] Entire polish pass — home page budget list, hero-like TBA section, more modern/thoughtful layout
- [ ] Command palette (add transaction, search/filter, budget actions, switch views)
- [ ] Custom reminder notifications (pay bills, etc.)
- [ ] Move money to/from a category with history of moves
- [ ] Auto distribute ready-to-assign funds to cover overspent categories
- [ ] Total overspent display

### Payees
- [ ] Payee management page (view, edit, merge, bulk operations)
- [ ] Multi-select merge with name selection and sanity check (transaction count preview)
- [ ] Auto-suggest merges via rapidfuzz — merge wizard with final review before commit
- [ ] Payee list: sort, filter/search, column alignment

### Transactions
- [ ] Split transaction button always accessible (outside scroll area), opens modal
- [ ] Split transaction "add remaining to category" button

### Data
- [ ] Backups and exports (CSV, YNAB-compatible)
- [ ] Auto backups (configurable frequency, count, age)

### Accounts & Finance Tools
- [ ] Savings tools section (personal finance flowchart, savings guidance)
- [ ] Education section (personal finance flowchart, other resources)
- [ ] Migrating to a new budget plan (preserve transaction history)
- [ ] Monthly category balance snapshots (O(1) budget summary, invalidate on change)
- [ ] Budget lookback / month comparison (side-by-side via snapshots)

### Localization
- [ ] Settings for currency, decimal vs comma separator, date format
- [ ] All numbers rounded to 2 decimal places throughout app

### Future Reports (deferred)
- [ ] Subscription tracker (detect recurring payments, show renewal cadence)
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
- [ ] Payee merge (deduplicate)
- [ ] Multi-currency support
- [ ] Plugin framework + plugin management page

---

## Completed

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
- [x] Payee analysis (top payees, recurring detection, monthly trend)
- [x] Day-of-week spending patterns
- [x] Event timeline / large transactions (annotated, limit toggle)
- [x] Transaction export (CSV / JSON) from reports page



ideas:
- create a mock api for dev instead of calling the simplefin api, it calls this and returns a static set of data. though it would have to be generated for a relevant time stamp or something?
